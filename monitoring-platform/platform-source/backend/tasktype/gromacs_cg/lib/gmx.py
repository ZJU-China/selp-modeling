"""GROMACS md.log / mdp parsing and run detection.

Pure parsing helpers operate on local file contents (logs are synced to the
task's local dir by the `route status` sync before gen_sim_status runs).
Run detection (gmx processes, SLURM squeue/sacct) goes through the SSH client.
"""
import os, re

RE_PERF = re.compile(r"Performance:\s*([\d.]+)\s*([\d.]+)")
RE_WALL = re.compile(r"^\s*Time:\s+[\d.]+\s+([\d.]+)")
RE_VERSION = re.compile(r"GROMACS\s*-\s*gmx\s+mdrun,\s*([\d.\-a-z]+)", re.I)
RE_STEP_ROW = re.compile(r"^\s*(\d+)\s+([\d.]+)")
RE_FLOAT = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

# Header lines that precede per-step rows (two observed layouts):
#   layout A: "Step Time"           then rows "step time [energy...]"
#   layout B: "           Step           Time"  then rows " 500 10.00000"
_RE_STEP_HDR = re.compile(r"\bStep\b.*\bTime\b")


def parse_md_log(path):
    """Parse a GROMACS mdrun log file (see parse_md_log_lines)."""
    try:
        with open(path, "r", errors="replace") as f:
            return parse_md_log_text(f.read())
    except (OSError, ValueError):
        return {}


def parse_md_log_text(text):
    """Parse GROMACS mdrun log content (already read into a string).

    Returns:
      step:            last step number
      time_ps:         simulated time (ps) at that step
      dt_ps:           timestep (ps) derived from step rows
      step_rows:       [(step, time_ps), ...]
      temps:           per-step temperatures when present in step rows
      energies:        per-step total energies when present in step rows
      temp_avg/min/max: from the final averages block
      energy_avg:       average total energy (kJ/mol) from the averages block
      perf_ns_day:      performance from the 'Performance:' line
      wall_s:           wall time (s) from the accounting table
      completed:        whether 'Finished mdrun' was printed
      version:          GROMACS version string
    """
    lines = text.splitlines()

    rows = []          # (step, time_ps)
    temps = []         # per-step temperatures if a temperature column exists
    energies = []      # per-step total energies if a column exists
    perf = None
    wall = None
    completed = False
    version = None
    avg_temp = avg_temp_min = avg_temp_max = None
    avg_energy = None
    averages_temps = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        if version is None:
            m = RE_VERSION.search(line)
            if m:
                version = "GROMACS " + m.group(1).strip()

        if "Performance:" in line:
            m = RE_PERF.search(line)
            if m:
                try:
                    perf = float(m.group(1))
                except ValueError:
                    perf = None

        m = RE_WALL.match(line)
        if m and wall is None:
            try:
                wall = float(m.group(1))
            except ValueError:
                wall = None

        if "Finished mdrun on rank 0" in line:
            completed = True

        # Step/Time header -> collect following numeric rows
        if _RE_STEP_HDR.search(line) and i + 1 < n and RE_STEP_ROW.match(lines[i + 1]):
            j = i + 1
            block = []
            while j < n:
                m = RE_STEP_ROW.match(lines[j])
                if not m:
                    break
                try:
                    step = int(m.group(1))
                    t = float(m.group(2))
                except ValueError:
                    j += 1
                    continue
                rest = lines[j].split()
                block.append((step, t, rest))
                j += 1
            if block:
                rows.extend(block)
                # If the header names a temperature column, capture it.
                hdr_tokens = line.split()
                if any("Tempe" in t for t in hdr_tokens):
                    temp_idx = next((k for k, t in enumerate(hdr_tokens) if "Tempe" in t), None)
                    if temp_idx is not None:
                        for _step, _t, rest in block:
                            if len(rest) > temp_idx:
                                try:
                                    temps.append(float(rest[temp_idx]))
                                except ValueError:
                                    pass
                # Total-energy column (layout A: step time poten kinen total)
                if block and len(block[0][2]) >= 5 and len(hdr_tokens) == 2:
                    for _step, _t, rest in block:
                        try:
                            energies.append(float(rest[4]))
                        except ValueError:
                            pass
            i = j
            continue

        # Averages block: 'Total Energy ... Temperature ...' header + value row
        if "Temperature" in line and "Energy" in line and i + 1 < n:
            m = RE_FLOAT.findall(lines[i + 1])
            if m and len(m) >= 3:
                try:
                    avg_temp = float(m[2])
                    avg_temp_min = avg_temp
                    avg_temp_max = avg_temp
                    avg_energy = float(m[0])
                    averages_temps.append(avg_temp)
                except ValueError:
                    pass

        i += 1

    step = rows[-1][0] if rows else 0
    time_ps = rows[-1][1] if rows else 0.0
    dt_ps = None
    if len(rows) >= 2:
        d = rows[-1][1] - rows[0][1]
        s = rows[-1][0] - rows[0][0]
        if s > 0 and d > 0:
            dt_ps = d / s

    if not avg_temp and temps:
        avg_temp = sum(temps) / len(temps)
        avg_temp_min = min(temps)
        avg_temp_max = max(temps)

    return {
        "step": step,
        "time_ps": time_ps,
        "dt_ps": dt_ps,
        "step_rows": rows,
        "temps": temps,
        "energies": energies,
        "temp_avg": round(avg_temp, 1) if avg_temp is not None else None,
        "temp_min": round(avg_temp_min, 1) if avg_temp_min is not None else None,
        "temp_max": round(avg_temp_max, 1) if avg_temp_max is not None else None,
        "energy_avg": round(avg_energy) if avg_energy is not None else None,
        "perf_ns_day": perf,
        "wall_s": wall,
        "completed": completed,
        "version": version,
    }


RE_MDP_DT = re.compile(r"^\s*dt\s*=\s*([\d.]+)", re.M)
RE_MDP_NSTEPS = re.compile(r"^\s*nsteps\s*=\s*(\d+)", re.M)
RE_MDP_TEMPERATURE = re.compile(r"^\s*(?:ref_t|temperature)\s*=\s*([\d.]+)", re.M)


def parse_mdp(path):
    """Parse a GROMACS mdp file for dt (ps), nsteps and reference temperature."""
    try:
        with open(path, "r", errors="replace") as f:
            text = f.read()
    except (OSError, ValueError):
        return {}
    result = {}
    m = RE_MDP_DT.search(text)
    if m:
        result["dt_ps"] = float(m.group(1))
    m = RE_MDP_NSTEPS.search(text)
    if m:
        result["nsteps"] = int(m.group(1))
    m = RE_MDP_TEMPERATURE.search(text)
    if m:
        result["ref_t"] = float(m.group(1))
    return result


def find_mdp_in_dir(dir_path, mdp_name="relax_out.mdp"):
    """Locate an mdp inside a sample dir (fall back to any *.mdp)."""
    candidates = [os.path.join(dir_path, mdp_name), os.path.join(dir_path, "md_out.mdp")]
    for c in candidates:
        if os.path.isfile(c):
            return c
    try:
        mdps = [f for f in os.listdir(dir_path) if f.endswith(".mdp")]
    except OSError:
        mdps = []
    if mdps:
        mdps.sort()
        return os.path.join(dir_path, mdps[0])
    return None


def summarize_sample(sample_dir, default_dt_ps=None, default_nsteps=None):
    """Combine an md.log + mdp into a single per-sample summary dict."""
    name = os.path.basename(sample_dir.rstrip("/"))
    mdlog = os.path.join(sample_dir, "relax.log")
    if not os.path.isfile(mdlog):
        mdlog = os.path.join(sample_dir, "md.log")
    if not os.path.isfile(mdlog):
        mdlog = os.path.join(sample_dir, "gromacs.log")
    if not os.path.isfile(mdlog):
        mdlog = None

    data = parse_md_log(mdlog) if mdlog else {}
    mdp_path = find_mdp_in_dir(sample_dir) if os.path.isdir(sample_dir) else None
    mdp = parse_mdp(mdp_path) if mdp_path else {}

    dt_ps = data.get("dt_ps") or mdp.get("dt_ps") or default_dt_ps
    nsteps = mdp.get("nsteps") or default_nsteps

    step = data.get("step") or 0
    time_ps = data.get("time_ps") or 0.0
    completed = bool(data.get("completed"))

    planned_ns = None
    if nsteps and dt_ps:
        planned_ns = nsteps * dt_ps / 1000.0
    ns_done = time_ps / 1000.0
    dt_fs = round(dt_ps * 1000) if dt_ps else None
    steps_per_ns = round(1000.0 / dt_ps) if dt_ps else None

    progress = 0.0
    if nsteps and nsteps > 0:
        progress = min(100.0, step / nsteps * 100.0)
    elif planned_ns and planned_ns > 0:
        progress = min(100.0, ns_done / planned_ns * 100.0)

    est_h = est_d = None
    if data.get("perf_ns_day") and planned_ns:
        remaining = max(0.0, planned_ns - ns_done)
        est_d = remaining / data["perf_ns_day"]
        est_h = est_d * 24

    wall_s = data.get("wall_s")
    if wall_s is None and data.get("perf_ns_day") and ns_done > 0:
        wall_s = ns_done / data["perf_ns_day"] * 86400

    status = "not_started"
    if step > 0:
        status = "running"
    if completed:
        status = "completed"

    return {
        "name": name,
        "sample_dir": sample_dir,
        "mdlog": mdlog,
        "mdp": mdp_path,
        "step": step,
        "time_ps": time_ps,
        "dt_ps": dt_ps,
        "dt_fs": dt_fs,
        "nsteps": nsteps,
        "planned_ns": round(planned_ns, 2) if planned_ns is not None else None,
        "ns_done": round(ns_done, 3),
        "steps_per_ns": steps_per_ns,
        "progress_pct": round(progress, 1),
        "temp_avg": data.get("temp_avg"),
        "temp_min": data.get("temp_min"),
        "temp_max": data.get("temp_max"),
        "energy_avg": data.get("energy_avg"),
        "perf_ns_day": data.get("perf_ns_day"),
        "wall_s": wall_s,
        "est_remaining_h": round(est_h, 1) if est_h is not None else None,
        "est_remaining_d": round(est_d, 1) if est_d is not None else None,
        "completed": completed,
        "status": status,
        "version": data.get("version"),
        "ref_t": mdp.get("ref_t"),
        "trace": data.get("temps"),
        "step_rows": data.get("step_rows") or [],
    }


# ---------------------------------------------------------------------------
# Remote run detection
# ---------------------------------------------------------------------------

def gmx_processes(ssh, cfg):
    """Return running gmx mdrun processes visible on the login host."""
    try:
        out, _, _ = ssh.exec(
            f'ps aux | grep -E "{cfg.ps_pattern()}" | grep -v grep || true',
            timeout=10,
        )
    except Exception:
        return []
    procs = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 11:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        cmd = line[line.index(parts[10]):]
        procs.append({"pid": pid, "command": cmd[:300]})
    return procs


def slurm_jobs(ssh, cfg):
    """Return the user's SLURM jobs matching the task's job prefix.

    Parses `squeue -u <user> -o %i\\t%j\\t%T` and, for jobs no longer queued,
    `sacct` (last day) so recently finished jobs are also reported.
    """
    user = cfg.slurm_user()
    prefix = cfg.slurm_job_prefix()
    jobs = []
    if not user:
        return jobs
    try:
        out, _, _ = ssh.exec(
            f'squeue -u {user} -h -o "%i\\t%j\\t%T" 2>/dev/null || true',
            timeout=15,
        )
    except Exception:
        out = ""
    for line in out.splitlines():
        fields = line.strip().split("\t")
        if len(fields) < 3:
            continue
        job_id, name, state = fields[0], fields[1], fields[2]
        if prefix and prefix not in name and prefix not in job_id:
            continue
        jobs.append({"jobId": job_id, "name": name, "state": state})
    return jobs


def is_running(ssh, cfg):
    """Combine gmx process + SLURM state into a single running flag."""
    procs = gmx_processes(ssh, cfg)
    if procs:
        return True, {"processes": procs, "jobs": []}
    jobs = slurm_jobs(ssh, cfg)
    active = [j for j in jobs if j["state"] in ("RUNNING", "PENDING", "COMPLETING", "CONFIGURING", "SUSPENDED")]
    return bool(active), {"processes": procs, "jobs": jobs}


def signal_or_scontrol(ssh, cfg, pgrep_signal, slurm_verb):
    """Pause/continue a GROMACS CG run.

    CG jobs normally run under SLURM on the ZJU cluster, so the correct control
    is `scontrol suspend|resume <jobid>` -- sending a signal to `gmx` on the
    login host would either miss the job entirely (it runs on a compute node)
    or leave SLURM reporting the job as RUNNING while the simulation is frozen.

    The job may also run unbatched (a plain interactive gmx on the login host),
    where there is no jobid; fall back to signalling the process then, matching
    the same "[n]" trick used elsewhere so pgrep does not match its own shell.
    """
    jobs = [j for j in slurm_jobs(ssh, cfg)
            if j["state"] in ("RUNNING", "PENDING", "CONFIGURING", "SUSPENDED")]
    if jobs:
        touched = []
        for j in jobs:
            # scontrol refuses to suspend a PENDING job; skip rather than fail
            # the whole call, so a queued job is not reported as an error.
            if j["state"] == "PENDING":
                continue
            ssh.exec(f"scontrol {slurm_verb} {j['jobId']} 2>&1 || true", timeout=20)
            touched.append(j["jobId"])
        return {"ok": bool(touched), "method": "slurm", "jobIds": touched,
                "action": f"{slurm_verb}d"}

    pattern = cfg.pgrep_pattern()
    count_out, _, _ = ssh.exec(
        f"pgrep -fc '[n]{pattern}' 2>/dev/null || echo 0", timeout=15
    )
    try:
        matched = int(count_out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        matched = 0
    ssh.exec(f"pkill -{pgrep_signal} -f '[n]{pattern}' 2>/dev/null; echo DONE", timeout=15)
    # ok reflects whether anything was actually signalled: pkill exits 1 when
    # nothing matched, and a pause that hit no process must not be reported as
    # having suspended the run.
    return {
        "ok": matched > 0,
        "method": "signal",
        "jobIds": [],
        "matchedProcesses": matched,
        "action": pgrep_signal,
        **({} if matched else
           {"note": f"No running gmx process matched '{pattern}', so {pgrep_signal} did nothing."}),
    }


def pause(ssh, cfg):
    return signal_or_scontrol(ssh, cfg, "STOP", "suspend")


def resume(ssh, cfg):
    return signal_or_scontrol(ssh, cfg, "CONT", "resume")


def is_paused(ssh, cfg):
    """True when every matching job is SUSPENDED rather than running."""
    jobs = [j for j in slurm_jobs(ssh, cfg) if j["state"] != "COMPLETED"]
    if not jobs:
        return False
    return all(j["state"] == "SUSPENDED" for j in jobs)


def remote_samples(ssh, cfg):
    """Expand the task's sampleGlobs into remote sample directory paths."""
    samples = []
    for pattern in cfg.sample_globs():
        pattern = pattern if pattern.endswith("/") else pattern + "/"
        try:
            out, _, _ = ssh.exec(f'ls -d {pattern} 2>/dev/null || true', timeout=15)
        except Exception:
            continue
        for line in out.splitlines():
            line = line.strip().rstrip("/")
            if line:
                samples.append(line)
    return samples


def remote_summaries(ssh, cfg, tail_bytes=400000):
    """Live per-sample summaries by streaming each remote md.log tail.

    The tail is large enough to include the final averages block for finished
    runs; for running jobs it still carries the latest Step/Time rows and the
    most recent statistics block.
    """
    mdlog_name = cfg.mdlog_name()
    summaries = []
    for sample in remote_samples(ssh, cfg):
        name = sample.rstrip("/").split("/")[-1]
        log = None
        for p in cfg.log_paths(name):
            out, _, code = ssh.exec(f'test -f "{p}" && echo YES', timeout=10)
            if "YES" in out:
                log = p
                break
        data = {}
        if log:
            out, _, _ = ssh.exec(f'tail -c {tail_bytes} "{log}" 2>/dev/null || true', timeout=30)
            data = parse_md_log_text(out)
        summaries.append({
            "name": name,
            "dir": sample,
            "mdlog": log,
            "step": data.get("step") or 0,
            "time_ps": data.get("time_ps") or 0.0,
            "dt_ps": data.get("dt_ps"),
            "temp_avg": data.get("temp_avg"),
            "energy_avg": data.get("energy_avg"),
            "perf_ns_day": data.get("perf_ns_day"),
            "wall_s": data.get("wall_s"),
            "completed": bool(data.get("completed")),
            "version": data.get("version"),
        })
    return summaries
