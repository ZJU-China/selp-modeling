"""Per-replica restart checkpoint inspection on the remote server.

Reads the latest .tcl in the task's configured checkpoint dir
(<remote_dir>/output/<replica>/ by default), extracts i_run/i_step and
reports which restart files (.coor/.vel/.xsc) exist, plus the latest
ENERGY step from the logs and whether NAMD is running.
"""

def read_checkpoints(ssh, cfg, steps_per_cycle=None):
    num_replicas = cfg.num_replicas
    parts = []
    for i in range(num_replicas):
        out_dir = cfg.checkpoint_dirs(i)[0]
        parts.append(
            f'echo "__CP{i}__" && (outDir="{out_dir}"; '
            f'latestTcl=$(ls -t "$outDir"/*.tcl 2>/dev/null | head -1); '
            f'if [ -z "$latestTcl" ]; then echo "NONE"; else '
            f'i_run=$(grep "set i_run" "$latestTcl" | awk \'{{print $NF}}\'); '
            f'i_step=$(grep "set i_step" "$latestTcl" | awk \'{{print $NF}}\'); '
            f'restartBase=$(echo "$latestTcl" | sed \'s/\\.tcl$//\'); '
            f'coorExists=$([ -f "${{restartBase}}.coor" ] && echo "true" || echo "false"); '
            f'velExists=$([ -f "${{restartBase}}.vel" ] && echo "true" || echo "false"); '
            f'xscExists=$([ -f "${{restartBase}}.xsc" ] && echo "true" || echo "false"); '
            f'echo "$i_run|$i_step|$coorExists|$velExists|$xscExists"; fi)'
        )

    log_globs = " ".join(f'"{p}"' for r in range(num_replicas) for p in cfg.log_paths(r))
    parts.append(f'echo "__STEP__" && (tail -n 30 {log_globs} 2>/dev/null | grep -oP \'ENERGY:\\s+\\K\\d+\' | tail -1 || echo 0)')
    parts.append(f'echo "__RUN__" && (pgrep -f "[n]{cfg.pgrep_pattern()}" >/dev/null 2>&1 && echo RUNNING || echo STOPPED)')
    parts.append(f'echo "__MTIME__" && (for f in {log_globs}; do find -L "$f" -mmin -{cfg.freshness_minutes()} -print 2>/dev/null; done | head -1 || echo 0)')

    raw, _, _ = ssh.exec(" && ".join(parts), timeout=30)

    checkpoints = []
    for i in range(num_replicas):
        marker = f"__CP{i}__"
        idx = raw.find(marker)
        if idx == -1:
            checkpoints.append({"replica": i, "found": False})
            continue
        next_marker = f"__CP{i + 1}__" if i < num_replicas - 1 else "__STEP__"
        next_idx = raw.find(next_marker, idx)
        line = raw[idx + len(marker): next_idx if next_idx != -1 else None].strip()
        if line == "NONE" or "|" not in line:
            checkpoints.append({"replica": i, "found": False})
            continue
        cycle, step, coor, vel, xsc = line.split("|")
        checkpoints.append({
            "replica": i, "found": True,
            "cycle": int(cycle) if cycle else 0,
            "step": int(step) if step else 0,
            "files": {"coor": coor == "true", "vel": vel == "true", "xsc": xsc == "true"},
        })

    running = False
    run_idx = raw.find("__RUN__")
    if run_idx != -1:
        running = raw[run_idx + len("__RUN__"):].strip() == "RUNNING"

    latest_step = 0
    step_idx = raw.find("__STEP__")
    if step_idx != -1:
        next_marker = raw.find("__RUN__", step_idx)
        val = raw[step_idx + len("__STEP__"): next_marker if next_marker != -1 else None].strip()
        try:
            latest_step = int(val) if val else 0
        except ValueError:
            latest_step = 0

    if not running:
        mtime = 0
        m_idx = raw.find("__MTIME__")
        if m_idx != -1:
            val = raw[m_idx + len("__MTIME__"):].strip().splitlines()
            if val:
                import re
                for line in val:
                    if line.strip():
                        mtime = 1
                        break
        if mtime:
            running = True

    steps_per_cycle = steps_per_cycle or cfg.steps_per_cycle
    return {
        "running": running,
        "latest_step": latest_step,
        "cycle": latest_step // steps_per_cycle if steps_per_cycle else 0,
        "checkpoints": checkpoints,
    }
