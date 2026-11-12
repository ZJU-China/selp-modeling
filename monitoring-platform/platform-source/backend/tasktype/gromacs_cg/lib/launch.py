"""Launch a GROMACS CG run on the server this task points at.

CG jobs were previously unstartable from the app: `start` and `restart` both
returned "GROMACS jobs run under SLURM; launch with sbatch on the cluster",
because the only deployment anyone had exercised was a hand-submitted sbatch
script on the ZJU cluster. Two consequences:

  * a flow step could not be started from the UI at all, and
  * the message named SLURM even on hosts that have none. The iGEM server has
    gmx 2025.4 on PATH and no SLURM at all, which is where the CG smoke run
    actually ran.

So this launches the same `grompp` + `mdrun` pair either way, and picks the
detachment strategy from what the host has:

  * sbatch present  -> write a batch script and submit it (the ZJU path)
  * otherwise       -> setsid so mdrun outlives the SSH session (local path)

Both paths are verified after launch rather than assumed: GROMACS exits
immediately on a bad topology or an over-large box, and reporting that as a
successful start hides the reason behind an empty log.
"""
import os
import shlex
import time

from _shared.tools import gmx_argv


def shell_quote(value):
    """Single-quote a value for the remote shell.

    Paths reach these commands from task_config.json, which the parameter panel
    writes from user input, so they are quoted rather than interpolated raw.
    """
    s = str(value)
    if s and all(c.isalnum() or c in "@%_+=:,./-" for c in s):
        return s
    return "'" + s.replace("'", "'\\''") + "'"


def probe_sbatch(ssh):
    """Return the sbatch path when the host has SLURM, else None."""
    out, _, code = ssh.exec("command -v sbatch 2>/dev/null || true", timeout=15)
    path = (out or "").strip().splitlines()
    if code == 0 and path:
        return path[0].strip()
    return None


def resolve_gmx(ssh, cfg):
    """Resolve the gmx command, checking it is executable on the host.

    The configured value wins, then GMX/GROMACS_BIN from the environment, then
    the shared default. A configured value that does not exist is an error
    rather than a reason to fall back: silently running a different binary than
    the task asked for makes the run irreproducible.
    """
    configured = cfg.gmx_bin()
    if configured:
        argv = shlex.split(configured)
        out, _, code = ssh.exec(f"command -v {shell_quote(argv[0])} >/dev/null 2>&1 && echo YES || echo NO",
                                timeout=15)
        if "YES" in (out or ""):
            return argv, {"source": "task config", "command": configured}
        # Not on PATH: accept an absolute path that exists anyway.
        out, _, _ = ssh.exec(f'test -x {shell_quote(argv[0])} && echo YES || echo NO', timeout=15)
        if "YES" in (out or ""):
            return argv, {"source": "task config (absolute path)", "command": configured}
        return None, {
            "source": "task config",
            "command": configured,
            "error": f"The configured gmx ({configured}) does not exist on this server.",
        }

    try:
        argv = gmx_argv(cfg.extra if isinstance(cfg.extra, dict) else None)
    except ValueError as e:
        return None, {"source": "resolver", "error": str(e)}
    out, _, _ = ssh.exec(f"command -v {shell_quote(argv[0])} >/dev/null 2>&1 && echo YES || echo NO",
                         timeout=15)
    if "YES" not in (out or ""):
        return None, {
            "source": "resolver",
            "command": " ".join(argv),
            "error": "gmx was not found on this server. Install GROMACS or set gromacs.gmxBin in the task config.",
        }
    return argv, {"source": "resolver", "command": " ".join(argv)}


def find_sample_dir(ssh, cfg):
    """Locate the directory holding this task's CG inputs.

    Prefers a configured runSubdir, then the sample globs, so a task that has
    actually been staged is started in place instead of in a fresh empty
    directory that would fail on a missing topology.
    """
    rd = (cfg.remote_dir or "").rstrip("/")
    if not rd:
        return None, "No remoteDir is configured for this task."
    sub = cfg.run_subdir()
    candidates = []
    if sub:
        candidates.append(f"{rd}/{sub}")
    for glob in cfg.sample_globs():
        g = glob if glob.startswith("/") else os.path.join(rd, glob)
        candidates.append(g.rstrip("/") if "*" not in g else g)
    for cand in candidates:
        if "*" in cand:
            out, _, _ = ssh.exec(f"ls -d {shell_quote(cand)} 2>/dev/null | head -1 || true", timeout=15)
            cand = (out or "").strip()
            if not cand:
                continue
        out, _, _ = ssh.exec(f"test -d {shell_quote(cand)} && echo YES || echo NO", timeout=15)
        if "YES" in (out or ""):
            return cand.rstrip("/"), None
    return None, f"No CG input directory found under {rd} (looked in: {', '.join(candidates)})."


def find_input(ssh, directory, names):
    """First of ``names`` that exists in ``directory``, else None."""
    for name in names:
        if not name:
            continue
        out, _, _ = ssh.exec(f"test -f {shell_quote(os.path.join(directory, name))} && echo YES || echo NO",
                             timeout=15)
        if "YES" in (out or ""):
            return os.path.join(directory, name)
    return None


def build_mdrun_command(gmx, cfg, sample_dir, tpr, resume=False):
    """The mdrun argv (no shell) for one sample.

    ``resume`` continues from the checkpoint, which is what a restart means for
    a partially completed MD run; starting over from the tpr would discard the
    trajectory already produced.
    """
    deffnm = cfg.defffnm() or "md"
    argv = [*gmx, "mdrun", "-s", tpr, "-deffnm", os.path.join(sample_dir, deffnm)]
    if resume:
        argv += ["-cpi", os.path.join(sample_dir, f"{deffnm}.cpt"),
                 "-append", "-deffnm", os.path.join(sample_dir, deffnm)]
    ntomp = cfg.ntomp()
    if ntomp > 0:
        argv += ["-ntomp", str(ntomp)]
    return argv


def _shell_join(argv):
    return " ".join(shell_quote(a) for a in argv)


def _launch_failure(ssh, sample_dir, stdout_log, launcher_log=None):
    """Explain a launch that did not survive, instead of reporting success."""
    out, _, _ = ssh.exec(f"tail -n 25 {shell_quote(stdout_log)} 2>/dev/null || true", timeout=20)
    detail = (out or "").strip()
    info = {
        "ok": False,
        "running": False,
        "error": "GROMACS exited during startup",
        "dir": sample_dir,
        "stdoutLog": stdout_log,
        "detail": detail[-800:] if detail else "no output in the mdrun log",
    }
    if launcher_log:
        lout, _, _ = ssh.exec(f"tail -n 20 {shell_quote(launcher_log)} 2>/dev/null || true", timeout=20)
        ldetail = (lout or "").strip()
        if ldetail:
            info["launcherLog"] = launcher_log
            info["launcherDetail"] = ldetail[-600:]
    return info


# How long to wait before each survival check. Two stages, because GROMACS can
# pass an early check and then die on a bad tpr. Overridable so tests do not
# spend real seconds sleeping.
SETTLE_DELAYS = (3, 4)

# Blacklist hwloc's GL component for every GROMACS invocation made here.
#
# hwloc_topology_load() runs a GL plugin that calls XOpenDisplay() while
# probing for a graphics device. On a login host whose X socket exists but no
# longer accepts an authorized client, that call blocks indefinitely, so mdrun
# never starts: the launch times out having printed "Authorization required,
# but no authorization protocol specified" and produced no log. GROMACS does
# not need GL to run on CPU, so the probe is skipped outright.
HWLOC_ENV = "HWLOC_COMPONENTS=-gl"


def start(ssh, cfg, resume=False, force=False):
    """Start the CG run. Returns a dict; ``ok`` says whether it is running."""
    if not (cfg.remote_dir or "").strip():
        return {"ok": False, "running": False,
                "error": "No remoteDir is configured. Set the remote working directory in the "
                         "Parameters panel before starting this step."}
    if (cfg.remote_dir or "").strip().upper().startswith("FILL-IN"):
        return {"ok": False, "running": False,
                "error": "This task still has its placeholder remote working directory. Set it in "
                         "the Parameters panel before starting."}

    gmx, gmx_info = resolve_gmx(ssh, cfg)
    if not gmx:
        return {"ok": False, "running": False, "error": gmx_info.get("error"), "gmx": gmx_info}

    sample_dir, err = find_sample_dir(ssh, cfg)
    if not sample_dir:
        return {"ok": False, "running": False, "error": err, "gmx": gmx_info}

    tpr = find_input(ssh, sample_dir, ["relax.tpr", "smoke.tpr", f"{cfg.defffnm()}.tpr"])
    if not tpr:
        # Not staged yet: run grompp so a start does not require a hidden
        # manual step.
        built = _build_tpr(ssh, cfg, gmx, sample_dir)
        if built.get("error"):
            return {"ok": False, "running": False, "error": built["error"],
                    "dir": sample_dir, "gmx": gmx_info, "grompp": built}
        tpr = built["tpr"]

    steps = cfg.smoke_steps()
    argv = build_mdrun_command(gmx, cfg, sample_dir, tpr, resume=resume)
    if steps:
        argv += ["-nsteps", str(steps)]

    deffnm = cfg.defffnm() or "md"
    stdout_log = os.path.join(sample_dir, f"{deffnm}_launcher.log")
    launcher_log = os.path.join(sample_dir, f"{deffnm}_submit.log")

    sbatch = probe_sbatch(ssh)
    if sbatch:
        result = _submit_slurm(ssh, cfg, sbatch, argv, sample_dir, stdout_log, launcher_log, deffnm, resume)
    else:
        # No scheduler on this host: detach so the run survives the SSH session
        # ending. Without setsid mdrun is killed when exec() returns.
        result = _launch_detached(ssh, argv, sample_dir, stdout_log, launcher_log, deffnm, resume)

    result.update({"gmx": gmx_info, "dir": sample_dir, "deffnm": deffnm, "resumed": bool(resume),
                   "stdoutLog": stdout_log,
                   "command": _shell_join(argv),
                   "scheduler": "sbatch" if sbatch else "setsid (no SLURM on this host)"})
    if result.get("error"):
        # The launch itself was refused (bad batch script, sbatch absent
        # mid-call, ...): no survival check can fix that, so say so now.
        return result

    # ``running`` above only means "submitted". Whether it stayed alive is what
    # the checks below decide, so a failure here is what surfaces an error. A
    # finished process is *not* a failure: a smoke run can complete inside the
    # settle window.
    for delay in SETTLE_DELAYS:
        if delay:
            time.sleep(delay)
        running, _ = _running(ssh, cfg)
        if not running:
            mdlog = os.path.join(sample_dir, f"{deffnm}.log")
            out, _, _ = ssh.exec(
                f"test -f {shell_quote(mdlog)} "
                f"&& grep -c 'Finished mdrun on rank 0' {shell_quote(mdlog)} 2>/dev/null || echo 0",
                timeout=15)
            if (out or "").strip().endswith("1") or "1\n" in out:
                result["running"] = False
                result["ok"] = True
                result["completed"] = True
                return result
            result.update(_launch_failure(ssh, sample_dir, stdout_log, launcher_log))
            return result
    result["running"] = True
    result["ok"] = True
    return result


def _launch_detached(ssh, argv, sample_dir, stdout_log, launcher_log, deffnm, resume):
    # hwloc's GL plugin calls XOpenDisplay() during topology detection. On a
    # host with a stale or auth-broken X socket that blocks forever, so mdrun
    # never reaches the first step and the launch just times out with
    # "Authorization required, but no authorization protocol specified".
    # Blacklisting the GL component skips the probe; GROMACS does not need it to
    # run on CPU. hwloc reads this at startup, so it is exported for the
    # detached process.
    inner = _shell_join(argv)
    launch_cmd = f"{HWLOC_ENV} {inner} > {shell_quote(stdout_log)} 2>&1"
    # shell_quote here quotes the whole inner script, so a path containing a
    # single quote (or a metacharacter) survives both layers.
    cmd = (f"cd {shell_quote(sample_dir)} && "
           f"setsid bash -c {shell_quote(launch_cmd)} "
           f"</dev/null > {shell_quote(launcher_log)} 2>&1 &")
    out, err_out, code = ssh.exec(cmd, timeout=20)
    return {"ok": True, "detached": True, "mode": "setsid", "running": False}


def _batch_script(cfg, argv, sample_dir, stdout_log, launcher_log, deffnm):
    """The sbatch script for this run.

    Written to the sample directory so the submission and the outputs it
    produces sit together, and so the script is inspectable afterwards -- an
    sbatch job that fails before its first step leaves no other trace.
    """
    cpus = cfg.ntomp() or 1
    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={deffnm}",
        f"#SBATCH --output={launcher_log}",
        f"#SBATCH --error={stdout_log}",
        "#SBATCH --ntasks=1",
        f"#SBATCH --cpus-per-task={max(1, cpus)}",
    ]
    if cfg.slurm_partition():
        lines.append(f"#SBATCH --partition={cfg.slurm_partition()}")
    if cfg.slurm_account():
        lines.append(f"#SBATCH --account={cfg.slurm_account()}")
    lines += [
        f"cd {shell_quote(sample_dir)} || exit 1",
        HWLOC_ENV,
        _shell_join(argv),
    ]
    return "\n".join(lines) + "\n"


def _submit_slurm(ssh, cfg, sbatch, argv, sample_dir, stdout_log, launcher_log, deffnm, resume):
    script = os.path.join(sample_dir, f"{deffnm}_run.sh")
    body = _batch_script(cfg, argv, sample_dir, stdout_log, launcher_log, deffnm)
    # heredoc rather than a quoted one-liner: the script has its own newlines
    # and quoting them for a single shell line would obscure what runs.
    write_cmd = f"cat > {shell_quote(script)} << 'SBATCH_SCRIPT_EOF_'\n{body}SBATCH_SCRIPT_EOF_\nchmod +x {shell_quote(script)}"
    _, err, code = ssh.exec(write_cmd, timeout=30)
    if code != 0:
        return {"ok": False, "running": False, "mode": "sbatch",
                "error": f"Could not write the batch script: {(err or '').strip()[:300]}"}
    out, err, code = ssh.exec(f"{shell_quote(sbatch)} {shell_quote(script)} 2>&1", timeout=60)
    text = (out or "").strip()
    if code != 0 or "Submitted batch job" not in text:
        return {"ok": False, "running": False, "mode": "sbatch", "script": script,
                "error": f"sbatch failed ({code}): {(text or (err or '')).strip()[:400]}"}
    job_id = text.split()[-1].strip()
    return {"ok": True, "running": True, "mode": "sbatch", "jobId": job_id,
            "script": script, "detached": True}


def _build_tpr(ssh, cfg, gmx, sample_dir):
    """Run grompp to produce a tpr from the staged inputs."""
    mdp = find_input(ssh, sample_dir, ["cg_input.mdp", cfg.mdp_name(), "md_out.mdp"])
    if not mdp:
        return {"error": "No .mdp input found in " + sample_dir +
                         " (looked for cg_input.mdp and " + cfg.mdp_name() + ")."}
    gro = find_input(ssh, sample_dir, [cfg.init_gro(), "init.gro", "start.gro"])
    if not gro:
        return {"error": "No starting coordinates found in " + sample_dir +
                         " (looked for " + cfg.init_gro() + ")."}
    deffnm = cfg.defffnm() or "md"
    tpr = os.path.join(sample_dir, f"{deffnm}.tpr")
    argv = [*gmx, "grompp", "-f", mdp, "-c", gro, "-p", cfg.topology() or os.path.dirname(mdp),
            "-o", tpr, "-maxwarn", "5"]
    out, err_out, code = ssh.exec(f"cd {shell_quote(sample_dir)} && {HWLOC_ENV} {_shell_join(argv)} 2>&1",
                                  timeout=180)
    if code != 0:
        return {"error": f"grompp failed ({code}): {(out or err_out or '')[-500:]}", "command": _shell_join(argv)}
    return {"tpr": tpr, "command": _shell_join(argv), "log": (out or "")[-400:]}


def _running(ssh, cfg):
    from tasktype.gromacs_cg.lib import gmx
    return gmx.is_running(ssh, cfg)