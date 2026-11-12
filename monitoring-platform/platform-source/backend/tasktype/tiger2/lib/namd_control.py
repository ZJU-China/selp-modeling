"""NAMD process control on remote server.

Process detection and file locations are task-specific (declared in the
task's task_config.json) and are accessed through the shared `TaskConfig`.
"""
import json, os, re, time

# Where a NAMD build is looked for when the task does not name one. The first
# entry is the long-standing convention; the rest are the layouts actually
# present on the group servers. An explicit setting always wins -- these are
# only consulted so a task that never configured a path still starts instead of
# failing against a hardcoded directory that may not exist.
DEFAULT_NAMD_BIN_GLOBS = [
    "~/software/NAMD_3.0.2_Linux-x86_64-netlrts-smp",
    "~/software/NAMD_3.0.2_Linux-x86_64-multicore",
    "~/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-netlrts-smp",
    "~/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-multicore",
    "~/NAMD_3.0.2_Linux-x86_64-netlrts-smp",
]

def _expand_home(path):
    """``~`` must be expanded remotely, not locally: the local home is the
    backend host's, and the launch runs on the compute server."""
    if path.startswith("~/"):
        return "$HOME/" + path[2:]
    return path

def probe_namd_bin(ssh, namd_bin):
    """Return (path, ok, detail) for a candidate NAMD directory.

    Both binaries must be present and executable. Checking only for the
    directory would let a partial or wrong-arch install pass and then fail
    deep inside charmrun, long after the launch was reported as accepted.
    """
    path = _expand_home(namd_bin)
    out, _, _ = ssh.exec(
        f'if [ -x "{path}/charmrun" ] && [ -x "{path}/namd3" ]; '
        f'then echo "{path}"; else echo "__NAMD_MISSING__"; fi',
        timeout=15,
    )
    got = (out or "").strip().splitlines()
    got = [g.strip() for g in got if g.strip()]
    if got and got[-1] != "__NAMD_MISSING__":
        return path, True, got[-1]
    return path, False, f"no executable charmrun+namd3 under {namd_bin}"

def resolve_namd_bin(ssh, cfg, namd_bin=None, globs=None):
    """Work out which NAMD build to launch, and prove it is usable.

    Order: explicit CLI value -> task's ``process.namdBin`` -> NAMD_BIN ->
    the known layout list. Anything that is set explicitly is *not* silently
    swapped out: if it is wrong the caller gets an error naming it, because a
    run quietly using a different build than the one configured is worse than
    a failed launch.
    """
    process = cfg.extra.get("process") or {}
    configured = namd_bin or cfg.namd_bin() or process.get("namdBin")
    candidates = [configured] if configured else list(
        globs if globs is not None else DEFAULT_NAMD_BIN_GLOBS
    )
    tried = []
    for cand in candidates:
        if not cand:
            continue
        path, ok, detail = probe_namd_bin(ssh, cand)
        if ok:
            return path, {"resolved": path, "source": "configured" if configured else "discovered",
                          "candidates": tried}
        tried.append(detail)
    return None, {"resolved": None, "source": None,
                  "error": "No usable NAMD build found.",
                  "detail": "; ".join(tried) or "no candidates configured",
                  "tried": tried}

def start(ssh, cfg, namd_bin=None, n_cores=None):
    """Start NAMD on the remote server in temp/.

    Core count comes from ``cfg.process.namdCores`` (default 32) so the MPI
    topology (``++n``/``++ppn``/``+replicas``) is a per-task setting instead of
    a hardcoded value.
    """
    remote_temp_dir = cfg.temp_dir()
    log_prefix = cfg.log_prefix
    num_replicas = cfg.num_replicas
    process = cfg.extra.get("process") or {}
    if n_cores is None:
        n_cores = int(process.get("namdCores", 32))

    # Resolve the build before anything is launched, so a missing NAMD is
    # reported as such instead of surfacing as a dead process and an empty log.
    namd_bin, resolve_info = resolve_namd_bin(ssh, cfg, namd_bin=namd_bin)
    if not namd_bin:
        return {"ok": False, "error": resolve_info["error"], "namd": resolve_info}

    # Find the latest config
    out, _, _ = ssh.exec(f"ls {remote_temp_dir}/{log_prefix}*.conf 2>/dev/null | tail -1")
    conf_path = out.strip()
    if not conf_path:
        out, _, _ = ssh.exec(f"ls {remote_temp_dir}/*.conf 2>/dev/null | tail -1")
        conf_path = out.strip()
    if not conf_path:
        return {"ok": False, "error": "No config file found"}

    name = os.path.splitext(os.path.basename(conf_path))[0]

    # Create all necessary directories (logs, output, output_root replicas)
    cfg.prepare_dirs(ssh)

    charmrun = os.path.join(namd_bin, "charmrun")
    namd3 = os.path.join(namd_bin, "namd3")
    stdout_log = os.path.join(remote_temp_dir, f"{name}_launcher.log")

    env_setup = cfg.env_setup()
    prefix = f"{env_setup}; " if env_setup else ""
    # Use setsid + disown to fully detach from SSH session so exec() returns
    cmd = (f"cd {remote_temp_dir} && {prefix}"
           f"setsid bash -c '"
           f"{charmrun} {namd3} ++local ++n {n_cores} ++ppn 1 +replicas {num_replicas} "
           f"{conf_path} "
           f"+stdout {remote_temp_dir}/logs/%d/{name}.%d.log "
           f"> {stdout_log} 2>&1' </dev/null &")
    out, err, code = ssh.exec(cmd, timeout=15)
    # Even if exit code is non-zero the background process may have started;
    # the important thing is that setsid detached it.  Verify with a quick
    # process check after a short wait.
    #
    # A single 3s check is not enough: NAMD can fail during its own startup
    # (a bad conf, a replica-count mismatch) and die after the check passes,
    # which used to be reported as a successful launch. So the process is
    # re-checked and the launcher log is read -- if the job is gone and the log
    # explains why, the launch failed, and the reason is returned.
    time.sleep(3)
    running = is_running(ssh, cfg)
    result = {"ok": True, "pid": "started", "detached": True, "running": running,
              "namd": resolve_info}
    if not running:
        result.update(_launch_failure(ssh, stdout_log))
    else:
        time.sleep(4)
        if not is_running(ssh, cfg):
            result.update(_launch_failure(ssh, stdout_log))
        else:
            result["running"] = True
    return result

def _launch_failure(ssh, stdout_log):
    """Explain a launch that did not survive, instead of reporting success."""
    out, _, _ = ssh.exec(f"tail -n 20 {stdout_log} 2>/dev/null", timeout=20)
    detail = (out or "").strip()
    return {
        "ok": False,
        "running": False,
        "error": "NAMD exited during startup",
        "launcherLog": stdout_log,
        "detail": detail[-800:] if detail else "no output in the launcher log",
    }

def stop(ssh, cfg):
    """Stop NAMD processes matching the log prefix.

    `[n]amd3` avoids pgrep/pkill matching the invoking shell's own command
    line (which otherwise contains the pattern literally)."""
    pattern = cfg.pgrep_pattern()
    out, _, _ = ssh.exec(f"pkill -f '[n]{pattern}' 2>/dev/null; echo DONE")
    return {"ok": True}

def signal(ssh, cfg, sig):
    """Send a signal to NAMD processes matching the log prefix.

    Used for pause/continue: `pkill -STOP`/`pkill -CONT` suspends and resumes
    the simulation without killing it, so a paused run keeps its accumulated
    state and resumes exactly where it stopped. `stop` (SIGTERM) is a different
    operation and must not be used for pause.

    The `[n]` prefix keeps pkill from matching the invoking shell's own command
    line, which otherwise contains the pattern literally.

    Reports how many processes were signalled. pkill exits 1 when nothing
    matched, but the caller treats a non-throwing result as success, so without
    an explicit count a pause that did nothing would be reported as having
    worked -- the UI would claim a running simulation is suspended while it
    keeps burning CPU.
    """
    pattern = cfg.pgrep_pattern()
    out, _, _ = ssh.exec(f"pkill -{sig} -f '[n]{pattern}' 2>/dev/null; echo DONE")
    # Count before/after is unreliable across the two round trips; instead ask
    # the shell how many matches the pattern had at signal time.
    count_out, _, _ = ssh.exec(f"pgrep -fc '[n]{pattern}' 2>/dev/null || echo 0")
    try:
        matched = int(count_out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        matched = 0
    return {
        "ok": matched > 0,
        "signal": sig,
        "matchedProcesses": matched,
        "note": None if matched else
                f"No running NAMD process matched '{pattern}', so {sig} did nothing.",
    }


def pause(ssh, cfg):
    return signal(ssh, cfg, "STOP")


def resume(ssh, cfg):
    return signal(ssh, cfg, "CONT")


def is_paused(ssh, cfg):
    """True when matching processes are stopped (state T/t) rather than running.

    SIGSTOPped processes stay in the process table, so the existing
    is_running() check reports them as running -- which is right, but it cannot
    distinguish paused from active. That distinction is what lets the UI show
    the real state instead of always claiming the run is progressing."""
    pattern = cfg.pgrep_pattern()
    out, _, _ = ssh.exec(
        f"ps -o state= -C namd3 2>/dev/null | grep -qE '^T' && echo PAUSED || echo ACTIVE"
    )
    return "PAUSED" in out


def is_running(ssh, cfg, freshness_s=None):
    """Check if NAMD is running.

    NAMD may run on the SSH host itself (local runs) or on a cluster
    compute node that writes logs to a shared filesystem (slurm + Lustre).
    Detect via a direct process match first, then fall back to freshness of
    the newest log (the compute node keeps appending to the shared log)."""
    pattern = cfg.pgrep_pattern()
    out, _, _ = ssh.exec(f"pgrep -f '[n]{pattern}' >/dev/null 2>&1 && echo YES || echo NO")
    if "YES" in out:
        return True
    minutes = freshness_s // 60 if freshness_s else cfg.freshness_minutes()
    minutes = max(1, minutes)
    for r in range(cfg.num_replicas):
        for p in cfg.log_paths(r):
            # `find -L` follows symlinks (plain stat -c %Y does not on some
            # filesystems, e.g. Lustre), so it sees the compute node's writes
            # even when logs/ entries are symlinks to a shared production dir.
            out, _, _ = ssh.exec(
                f"find -L {p} -mmin -{minutes} -print 2>/dev/null | grep -q . && echo FRESH || echo STALE"
            )
            if "FRESH" in out:
                return True
    return False

def _latest_step(ssh, candidates):
    latest_step = 0
    for log in candidates:
        out, _, _ = ssh.exec(f"tail -100 {log} 2>/dev/null | grep 'ENERGY:' | tail -1 | awk '{{print $2}}' || echo 0")
        try:
            step = int(out.strip())
            if step > latest_step:
                latest_step = step
        except ValueError:
            pass
    return latest_step

def status(ssh, cfg, steps_per_cycle=None, total_cycles=None):
    """Get NAMD status: running, latest step, etc."""
    running = is_running(ssh, cfg)

    latest_step = 0
    for r in range(cfg.num_replicas):
        step = _latest_step(ssh, cfg.log_paths(r))
        if step > latest_step:
            latest_step = step

    steps_per_cycle = steps_per_cycle or cfg.steps_per_cycle
    total_cycles = total_cycles or cfg.total_cycles
    total_steps = total_cycles * steps_per_cycle
    cycle = latest_step // steps_per_cycle if latest_step else 0
    progress = round(latest_step / total_steps * 100, 1) if total_steps > 0 else 0

    return {
        "running": running,
        "step": latest_step,
        "cycle": cycle,
        "progress_pct": progress,
        "total_steps": total_steps,
    }
