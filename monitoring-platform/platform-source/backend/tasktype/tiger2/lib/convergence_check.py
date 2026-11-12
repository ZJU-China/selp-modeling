"""Multi-metric convergence check from cached DCD trajectories.

Part of the shared TIGER2 tasktype. Thresholds, block/recent-window sizes and
the metric set can be overridden per task via task_config.json (section
`convergence`), falling back to the defaults below.

Reads:  <task>/cache/trajectory/ (topology.pdb/psf, replica_*.dcd)
Writes: <task>/cache/_convergence_state.json (stable-check counter)
Returns: result dict (see run_check).

Per-metric convergence criteria:
  - Split each replica's metric trace into blocks of `block_size` cycles.
  - Compare the last two complete blocks:
    |mean_i - mean_{i-1}| < mean_threshold (unit)
    AND max(std_i, std_{i-1}) / min(std_i, std_{i-1}) < std_ratio_threshold
  - All replicas must pass for `required_stable_checks` consecutive calls.
"""
import json, os, glob
import numpy as np

BLOCK_SIZE = 25  # cycles per block (25 cycles = 1 restart interval)
REQUIRED_STABLE_CHECKS = 3
RECENT_WINDOW = 100  # cycles shown in the recent-cycles chart window

METRICS = {
    "e2e": {
        "label": "End-to-end distance",
        "unit": "nm",
        "block_size": 25,
        "mean_threshold": 1.5,   # nm (relaxed)
        "std_ratio_threshold": 2.5,
    },
    "rg": {
        "label": "Radius of gyration",
        "unit": "nm",
        "block_size": 25,
        "mean_threshold": 0.4,   # nm (relaxed)
        "std_ratio_threshold": 2.5,
    },
}

def _apply_task_config(metrics):
    """Merge per-task convergence overrides into the metric specs."""
    merged = {}
    for key, spec in METRICS.items():
        merged[key] = dict(spec)
        if key in metrics:
            merged[key].update({k: v for k, v in metrics[key].items() if k != "compute"})
    return merged

def e2e_value(protein, ca):
    """End-to-end distance in nm from CA endpoints (fallback: protein endpoints)."""
    if ca.n_atoms >= 2:
        return float(np.linalg.norm(ca.positions[-1] - ca.positions[0]) / 10.0)
    return float(np.linalg.norm(protein.positions[-1] - protein.positions[0]) / 10.0)

def rg_value(protein, ca):
    """Radius of gyration in nm."""
    return float(protein.radius_of_gyration() / 10.0)

for _key, _spec in METRICS.items():
    if _key == "e2e":
        _spec["compute"] = e2e_value
    elif _key == "rg":
        _spec["compute"] = rg_value

def find_base_cycle(cache_dir, rep, steps_per_cycle):
    """Compute the global cycle of DCD frame 0 for this replica.

    The cached replica_{r}.dcd is the MERGED trajectory that starts at the very
    beginning of the run (frame 0 = cycle 1), so its base cycle is 0 regardless
    of restarts. The earliest synced NAMD log (sibling <cache_dir>/../logs/<rep>/)
    records absolute steps; its first step is the run start, so the base cycle =
    first step of the earliest-starting log / steps_per_cycle. Tasks that only
    synced a single (later) segment keep their correct base via the same rule.
    """
    log_dir = os.path.join(cache_dir, "..", "logs", str(rep))
    best = None
    if os.path.isdir(log_dir):
        for fname in os.listdir(log_dir):
            if not fname.endswith(".log"):
                continue
            first = None
            try:
                with open(os.path.join(log_dir, fname), "r", errors="replace") as fh:
                    for line in fh:
                        if line.startswith("ENERGY:"):
                            parts = line.split()
                            if len(parts) >= 13:
                                s = int(parts[1])
                                if first is None:
                                    first = s
                                break
            except Exception:
                continue
            if first is not None and (best is None or first < best):
                best = first
    if best is not None and steps_per_cycle:
        return best // steps_per_cycle
    return 0

def extract_metrics(topo, dcd_path, steps_per_cycle, metrics, base_cycle=0, max_frames=None):
    """Single pass over the trajectory, returning (steps, {metric: values}) for all metrics."""
    from MDAnalysis import Universe
    u = Universe(topo, dcd_path)
    protein = u.select_atoms("protein")
    if protein.n_atoms == 0:
        protein = u.atoms
    ca = u.select_atoms("name CA")
    values = {key: [] for key in metrics}
    steps = []
    n_frames = u.trajectory.n_frames
    limit = min(n_frames, max_frames) if max_frames else n_frames
    for i, ts in enumerate(u.trajectory):
        if i >= limit:
            break
        steps.append((base_cycle + ts.frame) * steps_per_cycle)
        for key, spec in metrics.items():
            values[key].append(round(float(spec["compute"](protein, ca)), 4))
    return steps, values

def block_average(values, block_size_cycles):
    """Group values into blocks of `block_size_cycles` cycles each.

    One DCD frame is written per cycle, so a block holds exactly
    `block_size_cycles` values (the last block may be partial).
    Returns (block_index, mean, std) for each block.
    """
    if not values:
        return []
    blocks = []
    n_per_block = max(1, block_size_cycles)
    for i in range(0, len(values), n_per_block):
        block = values[i:i + n_per_block]
        if len(block) >= 2:
            blocks.append({
                "idx": i // n_per_block,
                "mean": float(np.mean(block)),
                "std": float(np.std(block, ddof=1)),
                "n": len(block),
            })
    return blocks

def check_convergence(blocks, mean_th, std_ratio_th, block_size_cycles):
    """Return True if the last 2 COMPLETE blocks meet convergence criteria."""
    complete = [b for b in blocks if b["n"] >= max(1, block_size_cycles)]
    empty = {"mean_diff": None, "std_ratio": None, "mean_prev": None, "mean_curr": None, "std_prev": None, "std_curr": None}
    if len(complete) < 2:
        return False, empty
    b_prev, b_curr = complete[-2], complete[-1]
    mean_diff = abs(b_curr["mean"] - b_prev["mean"])
    std_min = min(b_curr["std"], b_prev["std"])
    std_max = max(b_curr["std"], b_prev["std"])
    std_ratio = std_max / std_min if std_min > 1e-10 else float("inf")
    converged = mean_diff < mean_th and std_ratio < std_ratio_th
    return converged, {
        "mean_diff": round(mean_diff, 4),
        "std_ratio": round(std_ratio, 4),
        "mean_prev": round(b_prev["mean"], 4),
        "mean_curr": round(b_curr["mean"], 4),
        "std_prev": round(b_prev["std"], 4),
        "std_curr": round(b_curr["std"], 4),
    }

def _load_task_overrides(local_dir, task_config_path=None):
    """Read per-task convergence overrides from the task's task_config.json.

    ``task_config_path`` (may be the absolute path passed via main.py's
    --task-config) is preferred; otherwise falls back to
    <local_dir>/scripts/task_config.json.
    """
    cfg_path = task_config_path or os.path.join(local_dir, "scripts", "task_config.json")
    try:
        with open(cfg_path) as f:
            data = json.load(f)
        conv = data.get("convergence") or {}
        metrics = conv.get("metrics") or {}
        return metrics, int(conv.get("requiredStableChecks", REQUIRED_STABLE_CHECKS)), int(conv.get("recentWindow", RECENT_WINDOW))
    except (OSError, ValueError):
        return {}, REQUIRED_STABLE_CHECKS, RECENT_WINDOW

def run_check(local_dir, steps_per_cycle=15000, task_key=None, task_config=None):
    """Run the full convergence check on cached trajectories for a task.

    local_dir = <task base dir> (cache lives at <local_dir>/cache).
    task_config = optional path to scripts/task_config.json; when given it is
    used instead of re-deriving <local_dir>/scripts/task_config.json.
    Returns the same result shape as the legacy root convergence_check.py.
    """
    from datetime import datetime, timezone

    metrics_override, required_stable, recent_window = _load_task_overrides(local_dir, task_config)
    metrics = _apply_task_config(metrics_override)

    task_key = task_key or os.path.basename(os.path.abspath(local_dir))
    cache_dir = os.path.join(local_dir, "cache")
    traj_dir = os.path.join(cache_dir, "trajectory")
    state_file = os.path.join(cache_dir, "_convergence_state.json")

    psf = os.path.join(traj_dir, "topology.psf")
    pdb = os.path.join(traj_dir, "topology.pdb")
    topo = psf if os.path.exists(psf) else (pdb if os.path.exists(pdb) else None)
    if not topo:
        return {"error": "No topology found", "converged": False}

    dcds = sorted(glob.glob(os.path.join(traj_dir, "replica_*.dcd")))
    if not dcds:
        return {"error": "No DCD files found", "converged": False}

    per_replica = {}
    metric_overall = {key: {"all_converged": True, "converged_replicas": 0} for key in metrics}
    all_converged = True

    for dcd_path in dcds:
        rep = int(os.path.basename(dcd_path).replace("replica_", "").replace(".dcd", ""))
        try:
            base_cycle = find_base_cycle(cache_dir, rep, steps_per_cycle)
            steps, values = extract_metrics(topo, dcd_path, steps_per_cycle, metrics, base_cycle=base_cycle)
            metrics_result = {}
            rep_converged = True
            for key, spec in metrics.items():
                blocks = block_average(values[key], spec["block_size"])
                ok, info = check_convergence(blocks, spec["mean_threshold"], spec["std_ratio_threshold"], spec["block_size"])
                recent = []
                for i in range(max(0, len(steps) - recent_window), len(steps)):
                    recent.append({"cycle": steps[i] // steps_per_cycle if steps_per_cycle else 0, "value": values[key][i]})
                metrics_result[key] = {
                    "converged": ok,
                    "n_blocks": len(blocks),
                    "last": values[key][-1] if values[key] else None,
                    "blocks": blocks[-5:] if blocks else [],
                    "recent_cycles": recent,
                    "details": info,
                }
                metric_overall[key]["all_converged"] = metric_overall[key]["all_converged"] and ok
                if ok:
                    metric_overall[key]["converged_replicas"] += 1
                if not ok:
                    rep_converged = False
            per_replica[str(rep)] = {
                "n_frames": len(steps),
                "last_e2e": metrics_result["e2e"]["last"],
                "last_rg": metrics_result["rg"]["last"],
                "converged": rep_converged,
                "metrics": metrics_result,
            }
            if not rep_converged:
                all_converged = False
        except Exception as e:
            per_replica[str(rep)] = {"error": str(e), "converged": False}
            all_converged = False

    state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file) as f:
                state = json.load(f)
        except:
            pass

    task_state = state.get(task_key, {"stable_count": 0})
    if all_converged:
        task_state["stable_count"] = task_state.get("stable_count", 0) + 1
    else:
        task_state["stable_count"] = 0
    task_state["last_check"] = str(datetime.now(timezone.utc))
    state[task_key] = task_state
    with open(state_file, "w") as f:
        json.dump(state, f)

    truly_converged = task_state["stable_count"] >= required_stable

    max_cycles = max((r.get("n_frames", 0) for r in per_replica.values()), default=0)
    block_size = metrics["e2e"]["block_size"]
    cycles_info = {
        "block_size": block_size,
        "recent_window": recent_window,
        "total": max_cycles,
        "in_block": ((max_cycles - 1) % block_size) + 1 if max_cycles > 0 else 0,
    }

    thresholds = {
        "metrics": {
            key: {
                "mean_diff": spec["mean_threshold"],
                "std_ratio": spec["std_ratio_threshold"],
                "block_size": spec["block_size"],
                "unit": spec["unit"],
            }
            for key, spec in metrics.items()
        },
        "mean_diff_nm": metrics["e2e"]["mean_threshold"],
        "std_ratio": metrics["e2e"]["std_ratio_threshold"],
        "block_size_cycles": metrics["e2e"]["block_size"],
    }

    return {
        "converged": truly_converged,
        "stable_checks": task_state["stable_count"],
        "required_checks": required_stable,
        "all_replicas_converged": all_converged,
        "all_metrics_converged": all(metric_overall[key]["all_converged"] for key in metrics),
        "stopped": task_state.get("stopped", False),
        "cycles": cycles_info,
        "metrics": metric_overall,
        "thresholds": thresholds,
        "replicas": per_replica,
    }
