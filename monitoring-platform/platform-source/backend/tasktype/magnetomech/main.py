#!/usr/bin/env python3
"""magnetomech tasktype entry point.

A local computation task: reads the GROMACS CG Young's modulus (network32
rubber elasticity) and computes the deformation of a magnetic-nanoparticle-
loaded SELP sample under an applied magnetic field.  Per-task parameters come
from the task's own <task_dir>/scripts/task_config.json.

Commands:
  magnetomech        (re)compute the field-deformation result into
                     <task_dir>/cache/magnetomech/ and print the JSON summary
  status/checkpoint  always {"running": false} (nothing runs remotely)
  progress/monitor   live { overall: {...} } read from cache/sim_status.json
  route              dispatch to routes/ (jobs/status/files/shell/sequences/trajectory)
  stop/start/restart not applicable -> informative error
  structure/cluster/gen-trajectory/convergence-check  local cache read or {}
"""
import argparse, json, os, subprocess, sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_SCRIPT_DIR)))
_BACKEND_ROOT = os.path.join(_REPO_ROOT, "backend")
sys.path.insert(0, _BACKEND_ROOT)
sys.path.insert(0, os.path.join(_BACKEND_ROOT, "tasktype"))

MAGNETOMECH_DIR = "cache/magnetomech"


def _resolve_python_bin():
    """Prefer the conda env that ships matplotlib (PNG rendering); the compute
    itself is pure stdlib so any of these runs it, but the final_simulation.png
    render needs matplotlib or Pillow."""
    env_bin = os.environ.get("PYTHON_BIN")
    if env_bin:
        return env_bin
    home = os.environ.get("HOME", "/home/selp")
    candidates = [
        os.path.join(home, ".local", "miniconda3", "envs", "igem2026", "bin", "python3"),
        "python3",
    ]
    for candidate in candidates:
        if os.path.isfile(candidate) or os.sep not in candidate:
            return candidate
    return "python3"


def parse_args():
    p = argparse.ArgumentParser(description="magnetomech tasktype")
    p.add_argument("command", nargs="?", default="status")

    p.add_argument("--host", default=None, help="Accepted for backend compatibility; magnetomech never contacts SSH")
    p.add_argument("--port", type=int, default=22)
    p.add_argument("--user", default=None, help="Accepted for backend compatibility; magnetomech never contacts SSH")
    p.add_argument("--key", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--local-dir", default=None)
    p.add_argument("--task-config", default=None)
    p.add_argument("--remote-dir", default=None)
    p.add_argument("--log-prefix", default=None)
    p.add_argument("--num-replicas", type=int, default=None)
    p.add_argument("--steps-per-cycle", type=int, default=None)
    p.add_argument("--total-cycles", type=float, default=None)
    p.add_argument("--namd-bin", default=None)

    p.add_argument("--route", default=None)
    p.add_argument("--sub", default=None)
    p.add_argument("--path", default=None)
    p.add_argument("--content", default=None)
    p.add_argument("--cmd", default=None)
    p.add_argument("--timeout", type=int, default=None)
    args, _ = p.parse_known_args()
    return args


def load_config(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _magnetomech_cache_dir(local_task):
    return os.path.join(local_task, MAGNETOMECH_DIR)


def _resolve_upstream_modulus_path(local_task):
    """Flow handoff: the predecessor's output is linked as input/flow-<prevId>.

    The rubber elasticity summary the gromacs_cg task wrote to its output/
    rubber_elasticity_summary.json is therefore readable here as
    input/flow-<prevId>/rubber_elasticity_summary.json.  Return the first such
    file when the user hasn't pinned an explicit modulusKpa/modulusPath.
    """
    input_dir = os.path.join(local_task, "input")
    try:
        entries = sorted(os.listdir(input_dir))
    except OSError:
        return None
    for entry in entries:
        if not entry.startswith("flow-"):
            continue
        candidate = os.path.join(input_dir, entry, "rubber_elasticity_summary.json")
        if os.path.isfile(candidate):
            return candidate
    return None


def _read_cached_result(local_task):
    path = os.path.join(_magnetomech_cache_dir(local_task), "magnetomech.summary.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def do_magnetomech(args, cfg, local_task):
    if not local_task:
        return {"ok": False, "error": "--local-dir is required"}
    mm = cfg.get("magnetomech") or {}
    explicit_kpa = mm.get("modulusKpa")
    modulus_path = mm.get("modulusPath")
    if not modulus_path and explicit_kpa in (None, "", 0):
        upstream = _resolve_upstream_modulus_path(local_task)
        if upstream:
            # Prefer the flow-chained gromacs_cg result over the repo static
            # summary; found upstream previously would have been a runtime
            # resolution only (no file was persisted in the task config).
            modulus_path = upstream
    params = {
        "modulusMode": mm.get("modulusMode") or "affine",
        "modulusKpa": explicit_kpa,
        "modulusPath": modulus_path,
        "particle": cfg.get("particle") or {},
        "field": cfg.get("field") or {},
        "temperatureK": cfg.get("temperatureK", 310.0),
        "coupling": cfg.get("coupling", 0.25),
        "demagFactor": cfg.get("demagFactor", 1.0 / 3.0),
    }
    # Composite (polymer / nanoparticle / water). Only passed
    # when it actually declares fractions, so a config without one keeps the
    # original single-fraction stiffness exactly.
    comp = cfg.get("composite")
    if isinstance(comp, dict):
        species = comp.get("species") if isinstance(comp.get("species"), dict) else comp
        if isinstance(species, dict) and any(v is not None for v in species.values()):
            params["composite"] = comp
    out_dir = _magnetomech_cache_dir(local_task)
    os.makedirs(out_dir, exist_ok=True)
    config_path = os.path.join(out_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False)

    run_script = os.path.join(_REPO_ROOT, "code", "magnetomech", "run.py")
    if not os.path.isfile(run_script):
        return {"ok": False, "error": "code/magnetomech/run.py not found in repo"}
    python_bin = _resolve_python_bin()
    try:
        proc = subprocess.run(
            [python_bin, run_script, "--config", config_path, "--output", out_dir],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "magnetomech computation timed out"}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout)[-2000:]}
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        return {"ok": False, "error": "unparseable output: %s" % proc.stdout[:1000]}
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "computation failed")}
    result["cacheDir"] = os.path.relpath(out_dir, local_task)
    return result


def main():
    args = parse_args()
    cfg = load_config(args.task_config)
    local_task = args.local_dir

    def do_route():
        from routes import dispatch
        return dispatch(None, cfg, args, local_task)

    def do_status():
        return {"running": False, "processes": [], "jobs": []}

    def do_checkpoint():
        return {"running": False}

    def do_progress():
        overall = {"avg_progress_pct": 0.0, "avg_step": 0,
                   "est_remaining_h": None, "est_remaining_d": None, "running": False}
        for candidate in (os.path.join(local_task, "sim_status.json"),
                          os.path.join(local_task, "cache", "sim_status.json")):
            if os.path.isfile(candidate):
                try:
                    with open(candidate, encoding="utf-8") as f:
                        overall = json.load(f).get("overall", overall)
                except (OSError, ValueError):
                    pass
                break
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

    def do_not_applicable():
        return {"ok": False, "error": "magnetomech is a local computation task; use the Field Deformation page"}

    def do_structure():
        result = _read_cached_result(local_task)
        return {"source": "local", "data": result} if result else {}

    commands = {
        "status": do_status,
        "checkpoint": do_checkpoint,
        "progress": do_progress,
        "monitor": do_monitor,
        "stop": lambda: {"ok": True, "running": False},
        "restart": do_not_applicable,
        "start": do_not_applicable,
        "route": do_route,
        "log-paths": lambda: {"ok": True, "message": "no remote paths for magnetomech tasks"},
        "magnetomech": lambda: do_magnetomech(args, cfg, local_task),
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