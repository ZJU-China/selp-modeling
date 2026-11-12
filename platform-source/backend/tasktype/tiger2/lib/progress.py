"""Progress estimation for simulation tasks.

Estimates simulation progress based on actual step data and
wall clock time, projecting completion time and remaining duration.
Log locations come from the task's TaskConfig.
"""
import json, os, time, statistics, glob

def _find_log(ssh, cfg, replica, timeout=5):
    """Discover the most recent active log file for a replica.
    Searches the task's configured log paths + a wildcard in each dir."""
    log_prefix = cfg.log_prefix
    remote_dir = cfg.remote_dir
    exact = " \\\n  ".join(cfg.log_paths(replica))
    dirs = " ".join(d for d in cfg.log_dirs(replica))
    script = f"""best=""; best_step=0
# Exact paths
for p in \\
  {exact}; do
  [ -f "$p" ] || continue
  s=$(tail -50 "$p" 2>/dev/null | grep 'ENERGY:' | tail -1 | awk '{{print $2}}')
  [ -n "$s" ] && [ "$s" -gt "$best_step" ] 2>/dev/null && {{ best="$p"; best_step="$s"; }}
done
# Wildcard: any {log_prefix}*.log in common dirs
for dir in {dirs}; do
  for p in "$dir"/{log_prefix}*.{replica}.log; do
    [ -f "$p" ] || continue
    s=$(tail -50 "$p" 2>/dev/null | grep 'ENERGY:' | tail -1 | awk '{{print $2}}')
    [ -n "$s" ] && [ "$s" -gt "$best_step" ] 2>/dev/null && {{ best="$p"; best_step="$s"; }}
  done
done
echo "$best"
"""
    out, _, _ = ssh.exec(script, timeout=timeout * 2)
    return out.strip()

def _read_steps_from_log(ssh, cfg, replica, timeout=10):
    """Get the latest step number from a remote NAMD log.
    Finds the active log and extracts the last ENERGY line."""
    log_path = _find_log(ssh, cfg, replica, timeout)
    if not log_path:
        return 0
    out, _, _ = ssh.exec(f"tail -50 {log_path} 2>/dev/null | grep 'ENERGY:' | tail -1 || true", timeout=timeout)
    if out.strip():
        parts = out.strip().split()
        if len(parts) >= 13:
            try: return int(parts[1])
            except: pass
    return 0

def estimate(ssh, cfg, local_task_dir, num_replicas=None):
    """Estimate simulation progress.

    Reads logs, computes step rate, estimates completion.
    Returns dict with actual and estimated progress metrics.
    """
    total_cycles = cfg.total_cycles
    steps_per_cycle = cfg.steps_per_cycle
    total_steps = total_cycles * steps_per_cycle
    num_replicas = int(num_replicas or cfg.num_replicas)

    current_steps = []
    rate = 0
    rate_samples = []

    for r in range(num_replicas):
        step = _read_steps_from_log(ssh, cfg, r)
        current_steps.append(step)

        log_path = _find_log(ssh, cfg, r)
        if log_path and step > 0:
            out2, _, _ = ssh.exec(f"grep 'PERFORMANCE:' {log_path} 2>/dev/null | tail -1 || true", timeout=5)
            if out2.strip():
                import re
                m1 = re.search(r'([\d.]+)\s+ns/day', out2)
                m2 = re.search(r'([\d.]+)\s+sec/step', out2)
                if m1:
                    ns_per_day = float(m1.group(1))
                    steps_per_ns = 250000.0  # 4fs timestep: 250 steps/ps = 250000 steps/ns
                    rate_samples.append(ns_per_day * steps_per_ns / 86400.0)
                elif m2:
                    rate_samples.append(1.0 / float(m2.group(1)))

    if rate_samples:
        srt = sorted(rate_samples)
        rate = srt[len(srt) // 2] if srt else 0

    avg_step = int(statistics.mean(current_steps)) if current_steps else 0
    actual_pct = round(avg_step / total_steps * 100, 1) if total_steps > 0 else 0

    est_remaining_h = None
    est_remaining_d = None
    if rate > 0 and avg_step < total_steps:
        remaining_steps = total_steps - avg_step
        est_remaining_s = remaining_steps / rate
        est_remaining_h = round(est_remaining_s / 3600, 1)
        est_remaining_d = round(est_remaining_h / 24, 1)

    completion_time = None
    if est_remaining_h is not None:
        completion_time = time.time() + est_remaining_h * 3600

    return {
        "config": {
            "total_cycles": total_cycles,
            "steps_per_cycle": steps_per_cycle,
            "total_steps": total_steps,
        },
        "replicas": {
            str(r): {
                "current_step": current_steps[r],
                "cycle": current_steps[r] // steps_per_cycle if steps_per_cycle else 0,
                "progress_pct": round(current_steps[r] / total_steps * 100, 1) if total_steps > 0 else 0,
            } for r in range(num_replicas)
        },
        "overall": {
            "avg_step": avg_step,
            "avg_progress_pct": actual_pct,
            "steps_per_second": round(rate, 2) if rate else None,
            "est_remaining_h": est_remaining_h,
            "est_remaining_d": est_remaining_d,
            "completion_timestamp": completion_time,
        },
    }
