"""Background simulation monitor.

Checks progress every N cycles, runs convergence check,
stops SLURM job when converged. Cadence comes from task_config.json
(monitor.intervalSeconds / monitor.cyclesPerCheck) falling back to the module
defaults; the SLURM job id and stop strategy are also task-specific
(task_config.json -> monitor.slurmJobId / monitor.stopCmd).
"""
import json, os, time, sys

DEFAULT_MONITOR_INTERVAL = 300
DEFAULT_CYCLES_PER_CHECK = 25
STATE_FILE = ".monitor_state.json"

def _interval(cfg):
    if cfg is not None and hasattr(cfg, "convergence"):
        monitor = cfg.extra.get("monitor") or {}
        return int(monitor.get("intervalSeconds", DEFAULT_MONITOR_INTERVAL))
    return DEFAULT_MONITOR_INTERVAL

def _cycles_per_check(cfg):
    if cfg is not None and hasattr(cfg, "convergence"):
        monitor = cfg.extra.get("monitor") or {}
        return int(monitor.get("cyclesPerCheck", DEFAULT_CYCLES_PER_CHECK))
    return DEFAULT_CYCLES_PER_CHECK

def _get_latest_step(ssh, cfg, replica, timeout=10):
    from lib.progress import _read_steps_from_log
    return _read_steps_from_log(ssh, cfg, replica, timeout)

def run_monitor(ssh, cfg, local_task_dir, steps_per_cycle=None, stop_cmd=None):
    """Run monitoring loop: check convergence every 25 cycles.
    Expects NAMD already running (e.g. via SLURM)."""
    state_path = os.path.join(local_task_dir, STATE_FILE)
    state = {"started": True, "last_cycle": 0, "stable_count": 0, "converged": False,
             "start_time": time.time()}

    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                state = json.load(f)
        except:
            pass

    from lib import convergence

    slurm_job_id = cfg.slurm_job_id()
    steps_per_cycle = steps_per_cycle or cfg.steps_per_cycle
    interval = _interval(cfg)
    cycles_per_check = _cycles_per_check(cfg)

    print("[Monitor] Entering main loop...", flush=True)
    while not state.get("converged"):
        time.sleep(interval)

        steps = []
        for r in range(int(cfg.num_replicas)):
            step = _get_latest_step(ssh, cfg, r)
            steps.append(step)

        max_step = max(steps) if any(steps) else 0
        current_cycle = max_step // steps_per_cycle if steps_per_cycle > 0 else 0
        print(f"[Monitor] Steps: {steps}, cycle: {current_cycle}", flush=True)

        last_max_step = state.get("last_max_step", 0)
        if max_step > 0:
            if max_step > last_max_step:
                state["last_progress_time"] = time.time()
            elif last_max_step > 0 and time.time() - state.get("last_progress_time", time.time()) > 7200:
                print("[Monitor] No progress for 2 hours, monitoring stopped.", flush=True)
                state["converged"] = True
                state["finished_time"] = time.time()
                _save_state(state, state_path)
                return state

        state["last_max_step"] = max_step
        state["last_cycle"] = current_cycle
        _save_state(state, state_path)

        last_check = state.get("last_check_cycle", 0)
        if current_cycle > 0 and current_cycle - last_check >= cycles_per_check:
            check_cycle = current_cycle - (current_cycle % cycles_per_check)
            state["last_check_cycle"] = check_cycle
            print(f"[Monitor] Cycle {current_cycle}: running convergence check...", flush=True)
            conv_state_path = os.path.join(local_task_dir, "cache", ".convergence_state.json")
            os.makedirs(os.path.dirname(conv_state_path), exist_ok=True)
            result = convergence.full_check(ssh, cfg, conv_state_path)
            print(f"[Monitor] Convergence result: converged={result.get('converged')}, "
                  f"all_replicas={result.get('all_converged')}, "
                  f"stable_checks={result.get('stable_checks')}/{result.get('required_checks')}",
                  flush=True)

            if result.get("converged"):
                print(f"[Monitor] CONVERGED at cycle {current_cycle}! Stopping SLURM job...", flush=True)
                if not stop_cmd:
                    stop_cmd = (f"scancel {slurm_job_id} 2>/dev/null || "
                                f"kill $(ps aux | grep namd3 | grep -v grep | awk '{{print $2}}') 2>/dev/null || true")
                out, _, _ = ssh.exec(stop_cmd, timeout=5)
                state["converged"] = True
                state["converged_at_cycle"] = current_cycle
                state["finished_time"] = time.time()
                _save_state(state, state_path)
                out2, _, _ = ssh.exec(f"squeue -h -j {slurm_job_id} 2>/dev/null || echo not_found", timeout=5)
                job_status = out2.strip()
                print(f"[Monitor] Job status after scancel: {job_status}", flush=True)
                print("[Monitor] Simulation complete.", flush=True)
                return state

    return state

def _save_state(state, path):
    try:
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"[Monitor] Failed to save state: {e}", flush=True)
