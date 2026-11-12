#!/usr/bin/env python3
"""gen_sim_status.py - Generate sim_status.json from synced GROMACS CG logs.

Usage: python3 gen_sim_status.py [task_dir] [output_path] [log_prefix]

The backend syncs each sample's md.log + mdp into <task_dir>/logs/<sample>/
(the task's own main.py `route status` command owns that sync), then runs this
script locally. It emits the SAME sim_status.json schema as the TIGER2
tasktype so the dashboard renders CG runs without frontend changes:

  config.num_replicas    number of monitored samples
  config.steps_per_cycle steps per simulated nanosecond (x-axis = ns)
  config.total_cycles    planned ns per sample
  config.total_steps     nsteps (per-sample production length)
  config.timestep_fs     real timestep from the sample mdp
  replicas[i]            one entry per sample (step, ns, temp, energy, ...)
"""
import os, re, sys, json, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.gmx import parse_md_log, find_mdp_in_dir, parse_mdp  # noqa: E402

DEFAULT_NUM_REPLICAS = 1
DEFAULT_STEPS_PER_CYCLE = 500000
DEFAULT_TOTAL_CYCLES = 10.0
DEFAULT_TIMESTEP_FS = 20.0
DEFAULT_PROTEIN = "2KY10 SELP CG"


def load_task_defaults(task_dir):
    path = os.path.join(task_dir, "scripts", "task_config.json")
    try:
        with open(path) as f:
            data = json.load(f)
        d = data.get("defaults") or {}
        g = data.get("gromacs") or {}
        return {
            "numReplicas": int(d.get("numReplicas", DEFAULT_NUM_REPLICAS)),
            "stepsPerCycle": int(d.get("stepsPerCycle", DEFAULT_STEPS_PER_CYCLE)),
            "totalCycles": float(d.get("totalCycles", DEFAULT_TOTAL_CYCLES)),
            "timestepFs": float(d.get("timestepFs", DEFAULT_TIMESTEP_FS)),
            "protein": d.get("protein", DEFAULT_PROTEIN),
            "forceField": d.get("forceField", "Martini 3.0.0"),
            "solvent": d.get("solvent", "CG water + ions"),
            "hmrMass": float(d.get("hmrMass", 0)),
            "tempMin": float(d.get("tempMin", 310)),
            "tempMax": float(d.get("tempMax", 310)),
            "mdlogName": g.get("mdlogName", "relax.log"),
            "plannedNs": float(g.get("plannedNs", d.get("totalCycles", DEFAULT_TOTAL_CYCLES))),
        }
    except (OSError, ValueError, TypeError):
        return {
            "numReplicas": DEFAULT_NUM_REPLICAS,
            "stepsPerCycle": DEFAULT_STEPS_PER_CYCLE,
            "totalCycles": DEFAULT_TOTAL_CYCLES,
            "timestepFs": DEFAULT_TIMESTEP_FS,
            "protein": DEFAULT_PROTEIN,
            "forceField": "Martini 3.0.0",
            "solvent": "CG water + ions",
            "hmrMass": 0.0,
            "tempMin": 310.0,
            "tempMax": 310.0,
            "mdlogName": "relax.log",
            "plannedNs": DEFAULT_TOTAL_CYCLES,
        }


def find_sample_dirs(task_dir):
    """logs/<sample>/ dirs, excluding the batch mdp holder."""
    logs_dir = os.path.join(task_dir, "logs")
    dirs = []
    if not os.path.isdir(logs_dir):
        return dirs
    for name in sorted(os.listdir(logs_dir)):
        p = os.path.join(logs_dir, name)
        if os.path.isdir(p) and not name.startswith("_"):
            dirs.append(p)
    return dirs


def find_mdlog(sample_dir, mdlog_name):
    for cand in (mdlog_name, "md.log", "gromacs.log", "relax.log"):
        p = os.path.join(sample_dir, cand)
        if os.path.isfile(p):
            return p
    try:
        logs = [f for f in os.listdir(sample_dir) if f.endswith(".log")]
    except OSError:
        logs = []
    if logs:
        logs.sort()
        return os.path.join(sample_dir, logs[0])
    return None


def summarize(sample_dir, mdlog_name, default_dt_ps, default_nsteps, planned_ns):
    name = os.path.basename(sample_dir.rstrip("/"))
    mdlog = find_mdlog(sample_dir, mdlog_name)
    data = parse_md_log(mdlog) if mdlog else {}

    mdp_path = find_mdp_in_dir(sample_dir, mdlog_name.replace(".log", "_out.mdp"))
    mdp = parse_mdp(mdp_path) if mdp_path else {}

    dt_ps = data.get("dt_ps") or mdp.get("dt_ps") or default_dt_ps
    nsteps = mdp.get("nsteps") or default_nsteps

    step = data.get("step") or 0
    time_ps = data.get("time_ps") or 0.0
    completed = bool(data.get("completed"))
    ns_done = time_ps / 1000.0
    dt_fs = round(dt_ps * 1000) if dt_ps else None
    steps_per_ns = round(1000.0 / dt_ps) if dt_ps else None

    if nsteps and nsteps > 0:
        progress = min(100.0, step / nsteps * 100.0)
    elif planned_ns and planned_ns > 0:
        progress = min(100.0, ns_done / planned_ns * 100.0)
    else:
        progress = 0.0

    est_h = est_d = None
    perf = data.get("perf_ns_day")
    if perf and planned_ns:
        remaining = max(0.0, planned_ns - ns_done)
        est_d = remaining / perf
        est_h = est_d * 24

    wall_s = data.get("wall_s")
    if wall_s is None and perf and ns_done > 0:
        wall_s = ns_done / perf * 86400

    status = "not_started"
    if step > 0:
        status = "running"
    if completed:
        status = "completed"

    # Temperature trace: use per-step temps when logged, else one point.
    temps = data.get("temps") or []
    rows = data.get("step_rows") or []
    trace = []
    if temps:
        rate = max(1, len(rows) // 200) if rows else 1
        n = min(len(rows), len(temps))
        for i in range(0, n, rate):
            trace.append({"step": rows[i][0], "temp": round(temps[i], 1)})
        if n > 0 and (n - 1) % rate != 0:
            trace.append({"step": rows[-1][0], "temp": round(temps[-1], 1)})
    if not trace and data.get("temp_avg") is not None:
        trace.append({"step": step, "temp": data["temp_avg"]})

    dcd_count = 0
    if os.path.isdir(sample_dir):
        try:
            dcd_count = len([f for f in os.listdir(sample_dir)
                             if f.endswith((".xtc", ".trr", ".dcd"))])
        except OSError:
            pass

    return {
        "name": name,
        "step": step,
        "time_ps": time_ps,
        "ns_done": round(ns_done, 3),
        "dt_fs": dt_fs,
        "steps_per_ns": steps_per_ns,
        "nsteps": nsteps,
        "planned_ns": round(planned_ns, 2) if planned_ns else None,
        "progress_pct": round(progress, 1),
        "temp_avg": data.get("temp_avg"),
        "temp_min": data.get("temp_min"),
        "temp_max": data.get("temp_max"),
        "energy_avg": data.get("energy_avg"),
        "perf_ns_day": perf,
        "wall_s": wall_s,
        "est_remaining_h": round(est_h, 1) if est_h is not None else None,
        "est_remaining_d": round(est_d, 1) if est_d is not None else None,
        "completed": completed,
        "status": status,
        "version": data.get("version"),
        "ref_t": mdp.get("ref_t"),
        "trace": trace,
        "dcd_count": dcd_count,
    }


def main():
    task_dir = os.path.expanduser(sys.argv[1]) if len(sys.argv) > 1 else os.path.expanduser(".")
    output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(task_dir, "sim_status.json")
    _log_prefix = sys.argv[3] if len(sys.argv) > 3 else "gromacs_cg"

    task_defaults = load_task_defaults(task_dir)

    # Batch-level mdp (logs/_batch/) supplies default dt/nsteps for samples
    # that have no mdp of their own.
    default_dt_ps = None
    default_nsteps = None
    batch_dir = os.path.join(task_dir, "logs", "_batch")
    if os.path.isdir(batch_dir):
        for f in sorted(os.listdir(batch_dir)):
            if f.endswith(".mdp"):
                mdp = parse_mdp(os.path.join(batch_dir, f))
                default_dt_ps = mdp.get("dt_ps")
                default_nsteps = mdp.get("nsteps")
                break

    sample_dirs = find_sample_dirs(task_dir)
    planned_ns = task_defaults["plannedNs"]

    summaries = [
        summarize(sd, task_defaults["mdlogName"], default_dt_ps, default_nsteps, planned_ns)
        for sd in sample_dirs
    ]
    if not summaries:
        summaries = [{
            "name": "none", "step": 0, "time_ps": 0.0, "ns_done": 0.0,
            "dt_fs": None, "steps_per_ns": None, "nsteps": None,
            "planned_ns": planned_ns, "progress_pct": 0.0,
            "temp_avg": None, "temp_min": None, "temp_max": None,
            "energy_avg": None, "perf_ns_day": None, "wall_s": None,
            "est_remaining_h": None, "est_remaining_d": None,
            "completed": False, "status": "not_started", "version": None,
            "ref_t": None, "trace": [], "dcd_count": 0,
        }]

    num_replicas = len(summaries)
    dt_fs = next((s["dt_fs"] for s in summaries if s["dt_fs"]), task_defaults["timestepFs"])
    steps_per_ns = next((s["steps_per_ns"] for s in summaries if s["steps_per_ns"]),
                        round(1e6 / dt_fs) if dt_fs else task_defaults["stepsPerCycle"])
    nsteps = next((s["nsteps"] for s in summaries if s["nsteps"]), None)
    total_steps = nsteps or round(steps_per_ns * planned_ns)
    total_cycles = planned_ns

    temp_min = task_defaults["tempMin"]
    temp_max = task_defaults["tempMax"]
    target_temps = [temp_max] * num_replicas
    running = False
    now = time.time()
    for s in summaries:
        mdlog = os.path.join(task_dir, "logs", s["name"], task_defaults["mdlogName"])
        if os.path.isfile(mdlog):
            try:
                if now - os.path.getmtime(mdlog) <= 300 and not s["completed"]:
                    running = True
                    break
            except OSError:
                pass

    replicas = {}
    sum_step = 0
    max_wall = 0
    total_remaining_ns = 0.0
    best_perf = None
    total_exchanges = 0
    temp_visit_counts = {}
    for i, s in enumerate(summaries):
        sum_step += s["step"]
        max_wall = max(max_wall, s["wall_s"] or 0)
        remaining = max(0.0, (s["planned_ns"] or planned_ns) - s["ns_done"])
        total_remaining_ns += remaining
        if s["perf_ns_day"]:
            best_perf = max(best_perf, s["perf_ns_day"]) if best_perf else s["perf_ns_day"]

        cycle = round(s["ns_done"], 2)

        replicas[str(i)] = {
            "id": i,
            "name": s["name"],
            "current_step": s["step"],
            "cycle": cycle,
            "progress_pct": s["progress_pct"],
            "temp_avg": s["temp_avg"] or 0,
            "temp_min": s["temp_min"] or 0,
            "temp_max": s["temp_max"] or 0,
            "total_energy_avg": s["energy_avg"] or 0,
            "exchange_count": 0,
            "wall_time_s": int(s["wall_s"]) if s["wall_s"] else 0,
            "est_remaining_h": s["est_remaining_h"],
            "est_remaining_d": s["est_remaining_d"],
            "temp_trace": s["trace"],
            "dcd_count": s["dcd_count"],
            "status": s["status"],
            "ns_done": s["ns_done"],
            "planned_ns": s["planned_ns"],
        }

    avg_step = sum_step // num_replicas if num_replicas else 0
    avg_progress = round(sum(s["progress_pct"] for s in summaries) / num_replicas, 1)

    overall_est_d = overall_est_h = None
    if best_perf and total_remaining_ns > 0:
        overall_est_d = round(total_remaining_ns / best_perf, 1)
        overall_est_h = round(overall_est_d * 24, 1)

    # Aggregate wall time + aggregate simulated ns (informational extras).
    aggregate_ns = round(sum(s["ns_done"] for s in summaries), 2)
    planned_aggregate_ns = round(planned_ns * num_replicas, 2)

    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "num_replicas": num_replicas,
            "steps_per_cycle": steps_per_ns,
            "total_cycles": round(total_cycles, 2),
            "total_steps": total_steps,
            "timestep_fs": dt_fs,
            "force_field": task_defaults["forceField"],
            "solvent": task_defaults["solvent"],
            "hmr_mass": task_defaults["hmrMass"],
            "protein": task_defaults["protein"],
            "temp_range": [temp_min, temp_max],
            "target_temps": target_temps,
            "md_replicas": num_replicas,
            "method": "GROMACS CG (Martini)",
            "gromacs": {
                "version": next((s["version"] for s in summaries if s["version"]), None),
                "planned_ns": round(planned_ns, 2),
                "aggregate_ns": aggregate_ns,
                "planned_aggregate_ns": planned_aggregate_ns,
                "samples": [s["name"] for s in summaries],
            },
        },
        "overall": {
            "avg_progress_pct": avg_progress,
            "avg_step": avg_step,
            "total_exchanges": total_exchanges,
            "est_remaining_h": overall_est_h,
            "est_remaining_d": overall_est_d,
            "running": running,
            "avg_temp_k": round(sum(s["temp_avg"] or 0 for s in summaries) / num_replicas, 1),
            "avg_energy_kj": round(sum(s["energy_avg"] or 0 for s in summaries) / num_replicas),
        },
        "replicas": replicas,
        "temp_visit_counts": temp_visit_counts,
    }

    tmp_path = output_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(result, f, indent=2)
    os.replace(tmp_path, output_path)

    print(f'OK samples={num_replicas} pct={avg_progress}% running={running} '
          f'wall={max_wall}s est_h={overall_est_h} dt={dt_fs}fs')


if __name__ == "__main__":
    main()
