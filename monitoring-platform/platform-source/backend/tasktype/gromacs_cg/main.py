#!/usr/bin/env python3
"""gromacs_cg tasktype entry point.

Every GROMACS (coarse-grained) task shares this code; per-task specifics come
from the task's own task_config.json (<task_dir>/scripts/task_config.json).
Backend services invoke it as:

    python3 main.py <command> --host H --port P --user U [--key K]
                              [--local-dir L] [--task-config C] [extra...]

Commands:
  status            running flag from gmx processes + SLURM state
  checkpoint        running flag + live per-sample step summary
  progress          live { overall: { avg_progress_pct, est_remaining_* } }
  monitor           long-running progress loop (JSON lines)
  route             dispatch to routes/ (files, shell, jobs, status)
  log-paths         resolved remote sample dirs / log / mdp paths
  stop              scancel matching SLURM jobs + kill visible gmx processes
  start             grompp (if needed) + detached mdrun; verified still running
  restart           as start, continuing from the checkpoint
  structure/cluster/gen-trajectory/convergence-check  not applicable -> {}
"""
import argparse, json, os, sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.join(_SCRIPT_DIR, "..", "..")
sys.path.insert(0, _BACKEND_ROOT)
sys.path.insert(0, _SCRIPT_DIR)

from _shared.ssh_client import SSHClient  # noqa: E402
from lib import gmx, launch  # noqa: E402


def parse_args():
    p = argparse.ArgumentParser(description="gromacs_cg tasktype")
    p.add_argument("command", nargs="?", default="status")

    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=22)
    p.add_argument("--user", required=True)
    p.add_argument("--key", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--local-dir", default=None)
    p.add_argument("--task-config", default=None)
    p.add_argument("--remote-dir", default=None)
    p.add_argument("--log-prefix", default=None)
    p.add_argument("--num-replicas", type=int, default=None)
    p.add_argument("--steps-per-cycle", type=int, default=None)
    p.add_argument("--total-cycles", type=float, default=None)

    # Route args (shared)
    p.add_argument("--route", default=None)
    p.add_argument("--sub", default=None)
    p.add_argument("--path", default=None)
    p.add_argument("--content", default=None)
    p.add_argument("--cmd", default=None)
    p.add_argument("--timeout", type=int, default=None)
    args, _ = p.parse_known_args()
    return args


def get_config(args):
    from lib.task_config import load, load_raw
    raw = load_raw(args.task_config) if args.task_config and os.path.exists(args.task_config) else {}
    return load(raw, cli_overrides={
        "remote_dir": args.remote_dir,
        "log_prefix": args.log_prefix,
        "num_replicas": args.num_replicas,
        "steps_per_cycle": args.steps_per_cycle,
        "total_cycles": args.total_cycles,
    })


def _overall_from_summaries(summaries, cfg):
    n = max(len(summaries), 1)
    done_ns = 0.0
    planned_ns = cfg.planned_ns()
    steps = []
    perf = []
    for s in summaries:
        steps.append(s["step"])
        if s["perf_ns_day"]:
            perf.append(s["perf_ns_day"])
        ns_done = s.get("time_ps", 0.0) / 1000.0
        if planned_ns and planned_ns > 0:
            done_ns += min(ns_done, planned_ns)
    avg_step = sum(steps) // n
    avg_pct = round(done_ns / (planned_ns * n) * 100, 1) if planned_ns and planned_ns > 0 else 0
    est_d = est_h = None
    if perf:
        remaining = max(0.0, planned_ns * n - done_ns)
        best = max(perf)
        if best > 0:
            est_d = round(remaining / best, 1)
            est_h = round(est_d * 24, 1)
    return {
        "avg_progress_pct": avg_pct,
        "avg_step": avg_step,
        "est_remaining_h": est_h,
        "est_remaining_d": est_d,
    }


def _analysis_summary(local_task):
    """Read the locally-written cache/analysis files into the /structure
    response shape (mirrors backend/services/analysis.js loadAnalysisToCache).
    """
    analysis_dir = os.path.join(local_task, "cache", "analysis")
    names = ["rg", "e2e", "rmsd", "ss", "energy", "box", "crosslink", "chainRg"]
    files = {
        "rg": "rg.dat", "e2e": "e2e.dat", "rmsd": "rmsd.dat", "ss": "ss.dat",
        "energy": "energy.dat", "box": "box.dat", "crosslink": "crosslink.dat",
        "crosslinkTable": "crosslink_table.tsv", "chainRg": "chain_rg.dat",
    }
    out = {"source": "local", "meta": None}
    for key, filename in files.items():
        path = os.path.join(analysis_dir, filename)
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    out[key] = f.read()
            except OSError:
                out[key] = None
        else:
            out[key] = None
    meta_path = os.path.join(analysis_dir, "meta.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                out["meta"] = json.load(f)
        except (OSError, ValueError):
            out["meta"] = None
    return out


def main():
    args = parse_args()
    cfg = get_config(args)
    ssh = SSHClient(host=args.host, port=args.port, user=args.user,
                    key_path=args.key, password=args.password)
    local_task = args.local_dir

    def do_route():
        from routes import dispatch
        return dispatch(ssh, cfg, args, local_task)

    def do_status():
        running, info = gmx.is_running(ssh, cfg)
        return {"running": running, "processes": info["processes"], "jobs": info["jobs"]}

    def do_checkpoint():
        running, info = gmx.is_running(ssh, cfg)
        return {"running": running, "jobs": info["jobs"], "processes": info["processes"]}

    def do_progress():
        running, _ = gmx.is_running(ssh, cfg)
        overall = {
            "avg_progress_pct": 0.0,
            "avg_step": 0,
            "est_remaining_h": None,
            "est_remaining_d": None,
        }
        status_path = None
        for candidate in (os.path.join(local_task, "sim_status.json"),
                          os.path.join(local_task, "cache", "sim_status.json")):
            if os.path.exists(candidate):
                status_path = candidate
                break
        if status_path:
            try:
                with open(status_path) as f:
                    local = json.load(f)
                overall = {
                    "avg_progress_pct": local["overall"].get("avg_progress_pct", 0.0),
                    "avg_step": local["overall"].get("avg_step", 0),
                    "est_remaining_h": local["overall"].get("est_remaining_h"),
                    "est_remaining_d": local["overall"].get("est_remaining_d"),
                }
            except Exception:
                pass
        overall["running"] = running
        return {"overall": overall, "samples": []}

    def do_monitor():
        import time
        try:
            while True:
                print(json.dumps(do_progress()), flush=True)
                time.sleep(10)
        except KeyboardInterrupt:
            pass
        return {}

    def do_stop():
        cmds = []
        if cfg.slurm_user():
            cmds.append(f'scancel -u {cfg.slurm_user()} 2>/dev/null || true')
        cmds.append(f'pkill -f "{cfg.pgrep_pattern()}" 2>/dev/null || true')
        for c in cmds:
            ssh.exec(c, timeout=10)
        running, info = gmx.is_running(ssh, cfg)
        return {"ok": not running, "running": running, "jobs": info["jobs"]}

    def do_pause():
        return gmx.pause(ssh, cfg)

    def do_continue():
        return gmx.resume(ssh, cfg)

    def do_log_paths():
        samples = gmx.remote_samples(ssh, cfg)
        details = {}
        for s in samples:
            name = s.rstrip("/").split("/")[-1]
            details[name] = {"dir": s, "logPaths": cfg.log_paths(name), "mdpPaths": cfg.mdp_paths(name)}
        return {"ok": True, "remoteDir": cfg.remote_dir, "samples": details}

    def do_start(resume=False):
        return launch.start(ssh, cfg, resume=resume)

    def do_structure():
        return _analysis_summary(local_task) if local_task else {}

    commands = {
        "status": do_status,
        "checkpoint": do_checkpoint,
        "progress": do_progress,
        "monitor": do_monitor,
        "stop": do_stop,
        "pause": do_pause,
        "continue": do_continue,
        "restart": lambda: do_start(resume=True),
        "start": lambda: do_start(resume=False),
        "route": do_route,
        "log-paths": do_log_paths,
        "structure": do_structure,
        "cluster": lambda: {},
        "gen-trajectory": lambda: {},
        "convergence-check": lambda: {},
    }
    result = commands.get(args.command, lambda: {"error": f"unknown command {args.command}"})()
    if result is None:
        result = {}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
