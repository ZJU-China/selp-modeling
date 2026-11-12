#!/usr/bin/env python3
"""Extract simulation data from TIGER2 logs and generate JSON for frontend."""
import json, re, sys, os
from datetime import datetime

def parse_log(log_path):
    """Parse a TIGER2 resume log for energy, timing, and temperature data."""
    energies = []
    timings = []
    temp_trace = []
    
    with open(log_path) as f:
        for line in f:
            if line.startswith("ENERGY:"):
                parts = line.split()
                if len(parts) >= 13:
                    step = int(parts[1])
                    temp = float(parts[12])
                    total = float(parts[11])
                    energies.append({"step": step, "total": total, "temp": round(temp, 1)})
                    temp_trace.append({"step": step, "temp": round(temp, 1)})
            elif line.startswith("TIMING:") and "Wall:" in line:
                m = re.search(r'TIMING:\s+(\d+)\s+.*Wall:\s+([\d.]+),\s+([\d.]+)/step', line)
                if m:
                    step = int(m.group(1))
                    wall_time = float(m.group(2))
                    ns_per_step = float(m.group(3))
                    timings.append({"step": step, "wall": round(wall_time, 1), "ns_per_step": ns_per_step})
    
    return energies, timings, temp_trace

def parse_history(hist_path):
    """Parse exchange history file. Format: step target_temp current_temp energy potential"""
    exchanges = []
    if not os.path.exists(hist_path):
        return exchanges
    with open(hist_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split()
                if len(parts) >= 4:
                    exchanges.append({
                        "step": int(parts[0]),
                        "target_temp": float(parts[1]),
                        "current_temp": float(parts[2]),
                        "energy": float(parts[3]),
                    })
    return exchanges

def main():
    base_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    prod_dir = os.path.join(base_dir, "production")
    
    replicas = {}
    all_temp_traces = []
    total_exchanges = 0
    config = {
        "num_replicas": 4,
        "steps_per_cycle": 15000,
        "total_cycles": 417,
        "total_steps": 6255000,
        "timestep_fs": 4.0,
        "target_temps": [365, 300, 314, 400],
        "temp_range": [280, 400],
        "force_field": "CHARMM36m",
        "solvent": "GBIS",
        "hmr_mass": 3.024,
        "protein": "2KY10 (750 aa SELP)",
    }
    
    for i in range(4):
        replica_dir = os.path.join(prod_dir, str(i))
        log_file = os.path.join(replica_dir, f"tiger2_resume50.{i}.log")
        hist_file = os.path.join(replica_dir, f"tiger2-prod.job1.{i}.history")
        
        if not os.path.exists(log_file):
            continue
        
        energies, timings, temp_trace = parse_log(log_file)
        exchanges = parse_history(hist_file)
        
        last_energy = energies[-1] if energies else None
        last_timing = timings[-1] if timings else None
        
        # Calculate progress
        current_step = last_energy["step"] if last_energy else 0
        resume_start = 750000  # cycle 50
        elapsed = current_step - resume_start
        remaining = config["total_steps"] - current_step
        progress_pct = round(current_step / config["total_steps"] * 100, 1)
        cycle = current_step // config["steps_per_cycle"]
        
        # Estimate remaining time
        if last_timing:
            ns_per_step = last_timing["ns_per_step"]
            est_remaining_s = remaining * ns_per_step
            est_remaining_h = round(est_remaining_s / 3600, 1)
            est_remaining_d = round(est_remaining_h / 24, 1)
        else:
            est_remaining_h = None
            est_remaining_d = None
        
        # Subsample temp trace (every 50 steps for chart)
        subsampled = temp_trace[::3]
        
        replicas[str(i)] = {
            "id": i,
            "current_step": current_step,
            "cycle": cycle,
            "progress_pct": progress_pct,
            "elapsed_steps": elapsed,
            "remaining_steps": remaining,
            "temp_avg": round(sum(t["temp"] for t in temp_trace) / len(temp_trace), 1) if temp_trace else 0,
            "temp_min": round(min(t["temp"] for t in temp_trace), 1) if temp_trace else 0,
            "temp_max": round(max(t["temp"] for t in temp_trace), 1) if temp_trace else 0,
            "total_energy_avg": round(sum(e["total"] for e in energies) / len(energies), 1) if energies else 0,
            "exchange_count": len(exchanges),
            "wall_time_s": last_timing["wall"] if last_timing else 0,
            "ns_per_step": last_timing["ns_per_step"] if last_timing else 0,
            "est_remaining_h": est_remaining_h,
            "est_remaining_d": est_remaining_d,
            "temp_trace": [{"step": t["step"], "temp": t["temp"]} for t in subsampled],
        }
        
        all_temp_traces.extend([{"step": t["step"], "temp": t["temp"], "replica": i} for t in subsampled])
        total_exchanges += len(exchanges)
    
    # Calculate overall stats
    if replicas:
        avg_progress = sum(r["progress_pct"] for r in replicas.values()) / len(replicas)
        avg_step = sum(r["current_step"] for r in replicas.values()) / len(replicas)
        min_remaining_h = min((r["est_remaining_h"] for r in replicas.values() if r["est_remaining_h"]), default=None)
    else:
        avg_progress = 0
        avg_step = 0
        min_remaining_h = None
    
    # Temperature visit counts
    temp_bins = {"280K": 0, "315K": 0, "355K": 0, "400K": 0}
    for t in all_temp_traces:
        temp = t["temp"]
        if temp < 297:
            temp_bins["280K"] += 1
        elif temp < 335:
            temp_bins["315K"] += 1
        elif temp < 377:
            temp_bins["355K"] += 1
        else:
            temp_bins["400K"] += 1
    
    output = {
        "timestamp": datetime.now().isoformat(),
        "config": config,
        "overall": {
            "avg_progress_pct": round(avg_progress, 1),
            "avg_step": int(avg_step),
            "total_exchanges": total_exchanges,
            "est_remaining_h": min_remaining_h,
            "est_remaining_d": round(min_remaining_h / 24, 1) if min_remaining_h else None,
            "running": True,
        },
        "replicas": replicas,
        "temp_visit_counts": temp_bins,
        "temp_trace_all": sorted(all_temp_traces, key=lambda x: x["step"]),
    }
    
    print(json.dumps(output, indent=2))

if __name__ == "__main__":
    main()
