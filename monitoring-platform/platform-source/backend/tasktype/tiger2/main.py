#!/usr/bin/env python3
"""
main.py - Unified control script for the shared TIGER2 task type.

Single entry point the backend uses for ALL task-specific judgments. It loads
the task's own config (backend/tasks/<taskId>/scripts/task_config.json) and
derives every task-specific string (remote file locations, process detection,
replica/cycle counts) from it, so per-task script copies are unnecessary.

Usage:
  python3 <tasktype>/tiger2/main.py <command> --task-config <task_config.json>
      --host HOST [--port P] [--user USER] [--key KEY]
      [--remote-dir DIR] [--log-prefix PREFIX] [--local-dir DIR]
      [--namd-bin PATH] [--cores N] [--num-replicas N]
      [--steps-per-cycle N] [--total-cycles N] [--output PATH]
      [--replica N] [--gen-pdb-script P] [--stop-cmd CMD]
      [--route NAME --sub OP --path P --content C --cmd CMD --timeout T]

Commands: start stop restart status sync converge convergence-check organize
          progress monitor checkpoint structure cluster trajectory-info
          gen-trajectory log-paths route
"""
import sys, os, json, argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.join(SCRIPT_DIR, "..", "..")
sys.path.insert(0, BACKEND_ROOT)
sys.path.insert(1, SCRIPT_DIR)
from _shared.ssh_client import SSHClient
from lib import namd_control, data_sync, convergence, progress, monitor, checkpoint, trajectory_info
from lib.task_config import load as load_config

def parse_args():
    p = argparse.ArgumentParser(description="TIGER2 shared task control")
    p.add_argument("command", choices=[
        "start", "stop", "restart", "status", "pause", "continue",
        "sync", "converge",
        "convergence-check", "organize", "progress", "monitor", "checkpoint",
        "structure", "cluster", "trajectory-info", "gen-trajectory", "log-paths",
        "route",
    ])
    p.add_argument("--task-config", default=None, help="Path to task_config.json")
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=22)
    p.add_argument("--user", required=True)
    p.add_argument("--key", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--remote-dir", default=None, help="Remote work dir (overrides task config)")
    p.add_argument("--local-dir", required=True, help="Local task dir (contains input/, logs/, output/)")
    p.add_argument("--log-prefix", default=None, help="NAMD log prefix (overrides task config)")
    p.add_argument("--namd-bin", default=None)
    p.add_argument("--cores", type=int, default=None, help="NAMD cores (default: process.namdCores from task config)")
    p.add_argument("--num-replicas", type=int, default=None)
    p.add_argument("--steps-per-cycle", type=int, default=None)
    p.add_argument("--total-cycles", type=int, default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--replica", type=int, default=0)
    p.add_argument("--gen-pdb-script", default=None)
    p.add_argument("--stop-cmd", default=None)
    p.add_argument("--route", default=None)
    p.add_argument("--sub", default=None)
    p.add_argument("--path", default=None)
    p.add_argument("--content", default=None)
    p.add_argument("--cmd", default=None)
    p.add_argument("--timeout", type=int, default=None)
    return p.parse_args()

def main():
    args = parse_args()

    cfg = load_config(
        args.task_config,
        remote_dir=args.remote_dir,
        log_prefix=args.log_prefix,
        num_replicas=args.num_replicas,
        steps_per_cycle=args.steps_per_cycle,
        total_cycles=args.total_cycles,
    )
    ssh = SSHClient(args.host, args.port, args.user, args.key, args.password)
    local_task = args.local_dir

    cmd = args.command
    if cmd == "start":
        r1 = data_sync.upload_input(ssh, cfg, os.path.join(local_task, "input"))
        r2 = data_sync.upload_config(ssh, cfg, os.path.join(local_task, "config"))
        r3 = namd_control.start(ssh, cfg, namd_bin=args.namd_bin, n_cores=args.cores)
        print(json.dumps({"upload": r1, "config": r2, "start": r3}))

    elif cmd == "stop":
        print(json.dumps(namd_control.stop(ssh, cfg)))

    elif cmd == "pause":
        # SIGSTOP, not SIGTERM: the run keeps its state and resumes from the
        # same step. "stop" above is a different operation (kill).
        print(json.dumps(namd_control.pause(ssh, cfg)))

    elif cmd == "continue":
        print(json.dumps(namd_control.resume(ssh, cfg)))

    elif cmd == "restart":
        namd_control.stop(ssh, cfg)
        data_sync.upload_input(ssh, cfg, os.path.join(local_task, "input"))
        data_sync.upload_config(ssh, cfg, os.path.join(local_task, "config"))
        print(json.dumps(namd_control.start(ssh, cfg, namd_bin=args.namd_bin, n_cores=args.cores)))

    elif cmd == "status":
        s = namd_control.status(ssh, cfg)
        s["remote_temp"] = cfg.temp_dir()
        s["local_dir"] = local_task
        print(json.dumps(s))

    elif cmd == "sync":
        print(json.dumps(data_sync.sync_all(ssh, cfg, local_task)))

    elif cmd == "converge":
        state_file = os.path.join(local_task, "cache", ".convergence_state.json")
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        print(json.dumps(convergence.full_check(ssh, cfg, state_file)))

    elif cmd == "convergence-check":
        from lib import convergence_check
        print(json.dumps(convergence_check.run_check(
            local_task, steps_per_cycle=cfg.steps_per_cycle,
            task_config=args.task_config)))

    elif cmd == "organize":
        print(json.dumps(data_sync.organize(ssh, cfg, local_task)))

    elif cmd == "progress":
        print(json.dumps(progress.estimate(ssh, cfg, local_task)))

    elif cmd == "monitor":
        print(json.dumps(monitor.run_monitor(ssh, cfg, local_task,
                                             steps_per_cycle=cfg.steps_per_cycle,
                                             stop_cmd=args.stop_cmd)))

    elif cmd == "checkpoint":
        print(json.dumps(checkpoint.read_checkpoints(ssh, cfg)))

    elif cmd == "log-paths":
        candidates = {"replicas": {}, "configs": cfg.config_paths()}
        for r in range(cfg.num_replicas):
            candidates["replicas"][str(r)] = cfg.log_paths(r)
        print(json.dumps(candidates))

    elif cmd == "structure":
        base_dir = cfg.analysis_dir()
        markers = ["rg", "e2e", "rmsd", "ss"]
        cmds = [f'echo "__{m.upper()}__" && (cat {base_dir}/{m}.dat 2>/dev/null || echo "NOT_FOUND")' for m in markers]
        raw, _, _ = ssh.exec(" && ".join(cmds), timeout=15)
        result: dict = {"rg": None, "e2e": None, "rmsd": None, "ss": None}
        for i, m in enumerate(markers):
            marker = f"__{m.upper()}__"
            idx = raw.find(marker)
            if idx == -1:
                continue
            next_marker = f"__{markers[i + 1].upper()}__" if i < len(markers) - 1 else None
            end = raw.find(next_marker, idx) if next_marker else -1
            val = raw[idx + len(marker): end if end != -1 else None].strip()
            if val and "NOT_FOUND" not in val:
                result[m] = val
        print(json.dumps(result))

    elif cmd == "cluster":
        raw, _, _ = ssh.exec(
            f'echo "__CLUST__" && (cat {cfg.analysis_dir()}/cluster_results.json 2>/dev/null || echo "NOT_FOUND") && '
            f'echo "__SCATTER__" && (cat {cfg.analysis_dir()}/cluster_scatter.json 2>/dev/null || echo "NOT_FOUND")',
            timeout=15,
        )
        result = {"clusters": None, "scatter": None}
        c_idx = raw.find("__CLUST__")
        s_idx = raw.find("__SCATTER__")
        if c_idx != -1 and s_idx != -1:
            cv = raw[c_idx + 8: s_idx].strip()
            if cv and "NOT_FOUND" not in cv:
                try:
                    i1, i2 = cv.index("{"), cv.rindex("}")
                    result["clusters"] = json.loads(cv[i1:i2 + 1])
                except Exception:
                    pass
        if s_idx != -1:
            sv = raw[s_idx + 11:].strip()
            if sv and "NOT_FOUND" not in sv:
                try:
                    i1, i2 = sv.index("{"), sv.rindex("}")
                    result["scatter"] = json.loads(sv[i1:i2 + 1])
                except Exception:
                    pass
        print(json.dumps(result))

    elif cmd == "trajectory-info":
        print(json.dumps(trajectory_info.discover(ssh, cfg)))

    elif cmd == "gen-trajectory":
        output = args.output or os.path.join(cfg.remote_dir, "trajectory.pdb")
        r = trajectory_info.gen_trajectory_pdb(ssh, cfg, output, args.replica, args.gen_pdb_script)
        if r["ok"]:
            local_pdb = os.path.join(local_task, "cache", "trajectory", "topology.pdb")
            r["downloaded"] = trajectory_info.download_trajectory_pdb(ssh, output, local_pdb)
        print(json.dumps(r))

    elif cmd == "route":
        from routes import dispatch
        print(json.dumps(dispatch(ssh, cfg, args, local_task)))

if __name__ == "__main__":
    main()
