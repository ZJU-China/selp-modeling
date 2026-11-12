"""Convergence monitoring using remote log files.

Reads NAMD log files via SSH, extracts energy data,
groups into blocks, and checks stability across replicas.
Thresholds come from the task's TaskConfig (convergence.metrics.energy),
falling back to the module defaults below when the task config omits them.
"""
import json, os, re, math

BLOCK_SIZE = 25
MEAN_THRESHOLD = 0.2
STD_RATIO_THRESHOLD = 2.0
REQUIRED_STABLE = 3

def _energy_metric(cfg):
    """Return the energy convergence thresholds for a task config.

    Reads `convergence.metrics.energy.{mean_threshold,std_ratio_threshold,
    block_size}` from the task's TaskConfig, defaulting to the module-level
    values so tasks without an explicit entry keep the historical behaviour.
    """
    metrics = None
    if cfg is not None and hasattr(cfg, "convergence_metrics"):
        metrics = cfg.convergence_metrics() or {}
    spec = (metrics or {}).get("energy") or {}
    return {
        "block_size": int(spec.get("block_size", BLOCK_SIZE)),
        "mean_threshold": float(spec.get("mean_threshold", MEAN_THRESHOLD)),
        "std_ratio_threshold": float(spec.get("std_ratio_threshold", STD_RATIO_THRESHOLD)),
    }

def _required_stable(cfg, required_stable=None):
    if required_stable is not None:
        return int(required_stable)
    if cfg is not None and hasattr(cfg, "convergence"):
        return int((cfg.convergence() or {}).get("requiredStableChecks", REQUIRED_STABLE))
    return REQUIRED_STABLE

def _mean(vals):
    return sum(vals) / len(vals)

def _std(vals, ddof=1):
    m = _mean(vals)
    var = sum((x - m) ** 2 for x in vals) / (len(vals) - ddof)
    return math.sqrt(var)

def parse_energy_from_log(ssh, remote_path):
    """Parse NAMD log file for ENERGY lines via SSH."""
    out, _, _ = ssh.exec(f"grep 'ENERGY:' {remote_path} 2>/dev/null | tail -500 || true")
    steps, energies = [], []
    for line in out.strip().split("\n"):
        if not line.startswith("ENERGY:"):
            continue
        parts = line.split()
        if len(parts) >= 13:
            try:
                steps.append(int(parts[1]))
                energies.append(float(parts[10]))
            except ValueError:
                pass
    return steps, energies

def block_average(values, n_blocks=BLOCK_SIZE):
    """Split values into blocks, return (mean, std) for each."""
    if not values or len(values) < 2:
        return []
    n = len(values)
    n_per_block = max(1, n // n_blocks)
    blocks = []
    for i in range(0, n, n_per_block):
        block = values[i:i + n_per_block]
        if len(block) >= 2:
            blocks.append((_mean(block), _std(block)))
    return blocks

def check_replica_stable(ssh, cfg, replica):
    """Check convergence for one replica using log energy data."""
    from lib.progress import _find_log
    log_path = _find_log(ssh, cfg, replica)
    if not log_path:
        return {"converged": False, "error": "no log found"}
    metric = _energy_metric(cfg)
    steps, energies = parse_energy_from_log(ssh, log_path)

    if len(steps) < 5:
        return {"converged": False, "error": "insufficient data", "n_frames": len(steps)}

    blocks = block_average(energies, n_blocks=metric["block_size"])
    if len(blocks) < 2:
        return {"converged": False, "error": "need 2+ blocks", "blocks": len(blocks)}

    m_prev, s_prev = blocks[-2]
    m_curr, s_curr = blocks[-1]
    mean_diff = abs(m_curr - m_prev)
    std_ratio = max(s_curr, s_prev) / min(s_curr, s_prev) if min(s_curr, s_prev) > 1e-10 else float("inf")
    conv = mean_diff < metric["mean_threshold"] and std_ratio < metric["std_ratio_threshold"]

    return {
        "converged": bool(conv),
        "mean_diff": round(mean_diff, 4),
        "std_ratio": round(std_ratio, 4),
        "n_frames": len(steps),
        "n_blocks": len(blocks),
        "last_energy": round(energies[-1] if energies else 0, 2),
    }

def check_all(ssh, cfg, num_replicas=None):
    """Check convergence across all replicas."""
    num_replicas = int(num_replicas or cfg.num_replicas)
    results = {}
    all_ok = True
    for r in range(num_replicas):
        res = check_replica_stable(ssh, cfg, r)
        results[str(r)] = res
        if not res.get("converged", False):
            all_ok = False
    return {
        "all_converged": all_ok,
        "replicas": results,
    }

def full_check(ssh, cfg, state_file=None, num_replicas=None, required_stable=None):
    """Full convergence check with state tracking."""
    result = check_all(ssh, cfg, num_replicas=num_replicas)
    required_stable = _required_stable(cfg, required_stable)

    if state_file and os.path.exists(state_file):
        try:
            with open(state_file) as f:
                state = json.load(f)
        except: state = {}
    else:
        state = {}

    stable_count = state.get("stable_count", 0)
    if result["all_converged"]:
        stable_count += 1
    else:
        stable_count = 0

    state["stable_count"] = stable_count
    if state_file:
        with open(state_file, "w") as f:
            json.dump(state, f)

    result["stable_checks"] = stable_count
    result["required_checks"] = required_stable
    result["converged"] = stable_count >= required_stable
    return result
