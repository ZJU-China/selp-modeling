#!/usr/bin/env python3
"""analyze.py - offline analysis of a GROMACS (coarse-grained) task's local cache.

Usage:
  python3 analyze.py <taskId> [--local-dir DIR] [--tasks-base DIR]

Reads the task's local cache/trajectory (topology.pdb + replica_*.dcd), the
  pulled output/ sample dirs (relax.gro, relax.xtc, relax.edr) and the network
  artifacts (input/network.json), then runs every analysis module — structure,
  energies, network, modulus — in isolation so a missing artifact only disables
  that feature. Writes under <task_dir>/cache/analysis:

  rg.dat e2e.dat rmsd.dat chain_rg.dat box.dat     (structure, A / nm)
  energy.dat                                       (energies, kJ/mol / K)
  crosslink.dat crosslink_table.tsv                (network, A)
  rubber_elasticity_summary.json                   (modulus: also copied to output/)
  meta.json                                        (stepsPerCycle, dtFs, results)

Prints a single JSON status line and exits 0 when at least one module produced
output. See lib/analysis/* for the per-module docs. Requires MDAnalysis
(conda env igem2026) for structure/network and a gmx binary for energies.
"""
import argparse
import datetime
import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.join(_SCRIPT_DIR, "..", "..")
sys.path.insert(0, _BACKEND_ROOT)
sys.path.insert(0, _SCRIPT_DIR)

from lib.analysis import paths, writers  # noqa: E402


def run_modules(task_dir, cfg):
    from lib.analysis import structure, energies, network, modulus

    modules = {}
    for name, mod in (("structure", structure), ("energies", energies), ("network", network), ("modulus", modulus)):
        try:
            modules[name] = mod.analyze(task_dir, cfg)
        except Exception as e:
            modules[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return modules


def main():
    p = argparse.ArgumentParser(description="GROMACS CG offline analysis")
    p.add_argument("task_id", nargs="?", default=None)
    p.add_argument("--local-dir", default=None)
    p.add_argument("--tasks-base", default=None)
    args = p.parse_args()

    if args.local_dir:
        task_dir = os.path.abspath(args.local_dir)
    else:
        task_id = args.task_id or ""
        base = args.tasks_base or os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", "tasks"))
        task_dir = os.path.join(base, task_id)

    if not os.path.isdir(task_dir):
        print(json.dumps({"ok": False, "error": f"task dir not found: {task_dir}"}))
        return 1

    os.makedirs(paths.analysis_dir(task_dir), exist_ok=True)
    cfg = paths.load_task_config(task_dir)
    modules = run_modules(task_dir, cfg)

    ok = any((m or {}).get("ok") for m in modules.values())
    errors = {k: v.get("error") for k, v in modules.items() if v.get("error")}

    meta = {
        "stepsPerCycle": cfg.get("stepsPerCycle"),
        "timestepFs": cfg.get("timestepFs"),
        "numReplicas": cfg.get("numReplicas"),
        "totalCycles": cfg.get("totalCycles"),
        "samples": paths.discover_samples(paths.output_dir(task_dir)),
        "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
        "modules": {k: {kk: vv for kk, vv in m.items() if kk != "error"}
                    for k, m in modules.items()},
    }
    writers.write_json(os.path.join(paths.analysis_dir(task_dir), "meta.json"), meta)

    print(json.dumps({"ok": ok, "modules": modules, "errors": errors}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())