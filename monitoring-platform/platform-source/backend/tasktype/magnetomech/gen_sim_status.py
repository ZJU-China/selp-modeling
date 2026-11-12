#!/usr/bin/env python3
"""gen_sim_status.py - magnetomech tasks never run a simulation, so write a
benign sim_status.json so the shared dashboard plumbing does not choke.

Usage: python3 gen_sim_status.py [task_dir] [output_path] [log_prefix]
"""
import json
import os
import sys


def main():
    task_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(task_dir, "sim_status.json")
    log_prefix = sys.argv[3] if len(sys.argv) > 3 else "magnetomech"

    config = {"numReplicas": 1, "stepsPerCycle": 1, "totalCycles": 1,
              "protein": "SELP + Fe3O4 magnetomech", "logPrefix": log_prefix}
    data = {
        "overall": {"avg_progress_pct": 0.0, "avg_step": 0,
                    "est_remaining_h": None, "est_remaining_d": None, "running": False},
        "config": config,
        "samples": [],
        "generatedBy": "magnetomech/gen_sim_status.py",
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(json.dumps({"ok": True, "output": output_path}))


if __name__ == "__main__":
    main()