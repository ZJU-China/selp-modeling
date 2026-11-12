#!/usr/bin/env python3
"""gen_sim_status.py - Generate sim_status.json from NAMD log files.
Usage: python3 gen_sim_status.py [tiger2_dir] [output_path] [log_prefix]

Replica/cycle counts default from the task's own task_config.json
(<tiger_dir>/scripts/task_config.json) when present; the synced NAMD conf
(values in tiger2_conf) still take precedence when it exists.
"""
import sys, os, json, re
from datetime import datetime, timezone

def load_task_defaults(tiger_dir):
    """Read numReplicas / stepsPerCycle / totalCycles from task_config.json."""
    path = os.path.join(tiger_dir, "scripts", "task_config.json")
    try:
        with open(path) as f:
            data = json.load(f)
        d = data.get("defaults") or {}
        return {
            "numReplicas": int(d.get("numReplicas", 4)),
            "stepsPerCycle": int(d.get("stepsPerCycle", 15000)),
            "totalCycles": int(d.get("totalCycles", 1667)),
            "protein": d.get("protein", "2KY10 SELP"),
        }
    except (OSError, ValueError, TypeError):
        return {"numReplicas": 4, "stepsPerCycle": 15000, "totalCycles": 1667, "protein": "2KY10 SELP"}

def resolve_log_dir(tiger_dir, replica):
    """Find log files: check logs/{r}/ first, then production/{r}/"""
    for d in ('logs', 'production'):
        p = os.path.join(tiger_dir, d, str(replica))
        if os.path.isdir(p):
            return p
    return os.path.join(tiger_dir, 'production', str(replica))

def resolve_output_dir(tiger_dir, replica):
    """Find output files: check output/{r}/ first, then production/{r}/"""
    for d in ('output', 'production'):
        p = os.path.join(tiger_dir, d, str(replica))
        if os.path.isdir(p):
            return p
    return os.path.join(tiger_dir, 'production', str(replica))

def find_latest_log(tiger_dir, replica, log_prefix):
    """Find latest log file for replica, checking logs/ then production/"""
    log_dir = resolve_log_dir(tiger_dir, replica)
    path = os.path.join(log_dir, f'{log_prefix}.{replica}.log')
    if os.path.exists(path):
        return path
    # fallback: any .log file
    if os.path.isdir(log_dir):
        logs = [f for f in os.listdir(log_dir) if f.endswith('.log')]
        if logs:
            logs.sort(key=lambda f: os.path.getmtime(os.path.join(log_dir, f)), reverse=True)
            return os.path.join(log_dir, logs[0])
    return None

def parse_energy_log(log_path):
    """Parse NAMD log file for ENERGY lines and TIGER2 swap info."""
    steps, temps, energies = [], [], []
    swap_count = 0
    first_timestep = 0
    s_per_step = None
    try:
        with open(log_path, 'r', errors='replace') as f:
            for line in f:
                if line.startswith('ENERGY:'):
                    parts = line.split()
                    if len(parts) >= 13:
                        steps.append(int(parts[1]))
                        energies.append(float(parts[10]))
                        temps.append(float(parts[12]))
                elif 'We are swapping' in line:
                    swap_count += 1
                elif s_per_step is None:
                    m = re.search(r'Initial time:.*?(\d+(?:\.\d+)?)\s+s/step', line)
                    if m:
                        s_per_step = float(m.group(1))
                    m2 = re.match(r'Info:\s+FIRST TIMESTEP\s+(\d+)', line)
                    if m2:
                        first_timestep = int(m2.group(1))
    except (FileNotFoundError, PermissionError):
        pass

    cut = 0
    for i in range(1, len(steps)):
        if steps[i] < steps[i - 1]:
            cut = i
    if cut > 0:
        steps = steps[cut:]
        temps = temps[cut:]
        energies = energies[cut:]

    trace = []
    n = len(steps)
    rate = max(1, n // 200)
    for i in range(0, n, rate):
        trace.append({'step': steps[i], 'temp': round(temps[i], 1)})
    if n > 0 and (n - 1) % rate != 0:
        trace.append({'step': steps[-1], 'temp': round(temps[-1], 1)})

    return {
        'steps': steps, 'temps': temps, 'energies': energies,
        'trace': trace, 'swaps': swap_count,
        'first_timestep': first_timestep, 's_per_step': s_per_step,
    }

def main():
    tiger_dir = os.path.expanduser(sys.argv[1]) if len(sys.argv) > 1 else os.path.expanduser('~/igem-2026/MD/TIGER2_2KY10')
    output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(tiger_dir, 'sim_status.json')
    log_prefix = sys.argv[3] if len(sys.argv) > 3 else 'tiger2_resume50'

    NUM_REPLICAS = 4
    STEPS_PER_CYCLE = 15000
    TOTAL_CYCLES = 417
    TOTAL_STEPS = 6255000
    TIMESTEP_FS = 4

    running = False
    try:
        import subprocess
        result = subprocess.run(['pgrep', '-f', f'[n]amd3 .*{log_prefix}'], capture_output=True, text=True, timeout=5)
        running = result.returncode == 0
    except Exception:
        pass
    if not running:
        # Cluster runs (slurm + shared fs) have no process visible here, but the
        # compute node keeps appending to the shared log: treat a fresh log as
        # running. (The backend route overrides `running` with the SSH status
        # check, so synced copies on the backend host do not affect the API.)
        import time
        now = time.time()
        for i in range(NUM_REPLICAS):
            p = find_latest_log(tiger_dir, i, log_prefix)
            if p and os.path.exists(p):
                try:
                    if now - os.path.getmtime(p) <= 300:
                        running = True
                        break
                except OSError:
                    pass

    tiger2_conf = {}
    # Conf may live next to the task dir (native host layout), in config/ (as
    # synced by the backend's sim-status sync), or under temp/ (alternate host
    # layout). Pick the first that exists so the config (num_runs, steps, etc.)
    # matches the actual run rather than falling back to defaults.
    conf_path = next(
        (p for p in (
            os.path.join(tiger_dir, f'{log_prefix}.conf'),
            os.path.join(tiger_dir, 'config', f'{log_prefix}.conf'),
            os.path.join(tiger_dir, 'temp', f'{log_prefix}.conf'),
        ) if os.path.exists(p)),
        None,
    )
    if conf_path:
        try:
            with open(conf_path) as f:
                for line in f:
                    m = re.match(r'\s*set\s+(\w+)\s+(.+)', line)
                    if m:
                        key = m.group(1)
                        val = m.group(2).strip().strip('"')
                        tiger2_conf[key] = val
        except Exception:
            pass

    base_conf = {}
    base_path = os.path.join(tiger_dir, 'tiger2_base.namd')
    if os.path.exists(base_path):
        try:
            with open(base_path) as f:
                for line in f:
                    m = re.match(r'\s*(\w+)\s+([\w.]+)', line)
                    if m:
                        base_conf[m.group(1)] = m.group(2)
        except Exception:
            pass

    task_defaults = load_task_defaults(tiger_dir)

    temp_min = int(tiger2_conf.get('t_min', tiger2_conf.get('min_temp', 280)))
    temp_max = int(tiger2_conf.get('t_max', tiger2_conf.get('max_temp', 400)))
    num_replicas = int(tiger2_conf.get('num_replicas', task_defaults['numReplicas']))
    steps_per_cycle = int(tiger2_conf.get('steps_equil1', 500)) + int(tiger2_conf.get('steps_sample', 12000)) + int(tiger2_conf.get('steps_equil2', 2500))
    total_cycles = int(tiger2_conf.get('num_runs', task_defaults['totalCycles']))
    total_steps = steps_per_cycle * total_cycles
    runs_per_frame = int(tiger2_conf.get('runs_per_frame', 5))
    frames_per_restart = int(tiger2_conf.get('frames_per_restart', 5))
    restart_interval = runs_per_frame * frames_per_restart

    NUM_REPLICAS = num_replicas
    TOTAL_CYCLES = total_cycles
    TOTAL_STEPS = total_steps

    target_temps = []
    for i in range(NUM_REPLICAS):
        t = temp_min + (temp_max - temp_min) * i / max(NUM_REPLICAS - 1, 1)
        target_temps.append(round(t))

    replicas = {}
    total_swaps = 0
    sum_step = 0
    max_wall_time = 0

    for i in range(NUM_REPLICAS):
        log_path = find_latest_log(tiger_dir, i, log_prefix)
        data = parse_energy_log(log_path) if log_path else {
            'steps': [], 'temps': [], 'energies': [],
            'trace': [], 'swaps': 0,
            'first_timestep': 0, 's_per_step': None,
        }

        step = data['steps'][-1] if data['steps'] else 0
        temp_avg = round(sum(data['temps']) / len(data['temps']), 1) if data['temps'] else 0
        temp_min_val = min(data['temps']) if data['temps'] else 0
        temp_max_val = max(data['temps']) if data['temps'] else 0
        energy_avg = round(sum(data['energies']) / len(data['energies'])) if data['energies'] else 0
        swaps = data['swaps']
        total_swaps += swaps
        sum_step += step

        cycle = step // STEPS_PER_CYCLE
        progress = round(step / TOTAL_STEPS * 100, 1) if TOTAL_STEPS > 0 else 0

        wall_time = 0
        est_h = None
        est_d = None
        first_ts = data['first_timestep']
        s_step = data['s_per_step']
        if s_step and step > first_ts:
            steps_done = step - first_ts
            wall_time = int(steps_done * s_step)
            remaining_steps = total_steps - step
            est_h = round(remaining_steps * s_step / 3600, 1)
            est_d = round(est_h / 24, 1) if est_h is not None else None

        if wall_time > max_wall_time:
            max_wall_time = wall_time

        # Count DCD files in output/
        output_dir = resolve_output_dir(tiger_dir, i)
        dcd_count = 0
        if os.path.isdir(output_dir):
            dcd_count = len([f for f in os.listdir(output_dir) if f.endswith('.dcd')])

        replicas[str(i)] = {
            'id': i, 'current_step': step, 'cycle': cycle, 'progress_pct': progress,
            'temp_avg': temp_avg, 'temp_min': round(temp_min_val, 1), 'temp_max': round(temp_max_val, 1),
            'total_energy_avg': energy_avg, 'exchange_count': swaps,
            'wall_time_s': wall_time, 'est_remaining_h': est_h, 'est_remaining_d': est_d,
            'temp_trace': data['trace'], 'dcd_count': dcd_count,
        }

    avg_step = sum_step // NUM_REPLICAS if NUM_REPLICAS > 0 else 0
    avg_progress = round(avg_step / TOTAL_STEPS * 100, 1) if TOTAL_STEPS > 0 else 0

    unique_swaps = total_swaps // 2

    overall_est_h = None
    overall_est_d = None
    overall_s_per_step = None
    for i in range(NUM_REPLICAS):
        log_path = find_latest_log(tiger_dir, i, log_prefix)
        data = parse_energy_log(log_path) if log_path else {'s_per_step': None}
        if data['s_per_step']:
            if overall_s_per_step is None or data['s_per_step'] > overall_s_per_step:
                overall_s_per_step = data['s_per_step']
    if overall_s_per_step and avg_step < total_steps:
        remaining_steps = total_steps - avg_step
        overall_est_h = round(remaining_steps * overall_s_per_step / 3600, 1)
        overall_est_d = round(overall_est_h / 24, 1)

    temp_visit_counts = {}
    for i in range(NUM_REPLICAS):
        log_path = find_latest_log(tiger_dir, i, log_prefix)
        data = parse_energy_log(log_path) if log_path else {'temps': []}
        for t in data['temps']:
            bucket = int(t / 35) * 35
            bucket = max(temp_min, min(temp_max, bucket))
            key = f'{bucket}K'
            temp_visit_counts[key] = temp_visit_counts.get(key, 0) + 1

    # Collect output file listing
    output_files = {}
    for i in range(NUM_REPLICAS):
        out_dir = resolve_output_dir(tiger_dir, i)
        if os.path.isdir(out_dir):
            files = sorted(os.listdir(out_dir))
            output_files[str(i)] = files

    cycle_time_ps = round(steps_per_cycle * TIMESTEP_FS / 1000, 2)
    replica_time_ns = round(total_cycles * cycle_time_ps / 1000, 2)
    aggregate_time_ns = round(replica_time_ns * num_replicas, 2)
    restart_step_interval = restart_interval * steps_per_cycle

    result = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'config': {
            'num_replicas': num_replicas, 'steps_per_cycle': steps_per_cycle,
            'total_cycles': total_cycles, 'total_steps': total_steps,
            'timestep_fs': TIMESTEP_FS, 'force_field': 'CHARMM36m', 'solvent': 'GBIS',
            'hmr_mass': 3.024, 'protein': task_defaults['protein'],
            'temp_range': [temp_min, temp_max], 'target_temps': target_temps,
            'steps_equil1': int(tiger2_conf.get('steps_equil1', 500)),
            'steps_sample': int(tiger2_conf.get('steps_sample', 12000)),
            'steps_equil2': int(tiger2_conf.get('steps_equil2', 2500)),
            'runs_per_frame': runs_per_frame, 'frames_per_restart': frames_per_restart,
            'restart_interval_cycles': restart_interval,
            'restart_step_interval': restart_step_interval,
            'cycle_time_ps': cycle_time_ps,
            'replica_time_ns': replica_time_ns,
            'aggregate_time_ns': aggregate_time_ns,
            'gbis': {
                'solvent_dielectric': float(base_conf.get('solventDielectric', 78.5)),
                'ion_concentration': float(base_conf.get('ionConcentration', 0.15)),
                'surface_tension': float(base_conf.get('surfaceTension', 0.005)),
            },
            'dynamics': {
                'rigid_bonds': base_conf.get('rigidBonds', 'all'),
                'cutoff': float(base_conf.get('cutoff', 16.0)),
                'switchdist': float(base_conf.get('switchdist', 15.0)),
                'pairlistdist': float(base_conf.get('pairlistdist', 18.0)),
                'langevin_damping': float(base_conf.get('langevinDamping', 1.0)),
                'langevin_temp': float(base_conf.get('langevinTemp', 280)),
            },
            'parallelism': {
                'cores': 16, 'replicas': num_replicas, 'ppn': 1,
                'charmrun_cmd': f'charmrun namd3 ++local ++n {num_replicas} ++ppn 1 +replicas {num_replicas}',
            },
        },
        'overall': {
            'avg_progress_pct': avg_progress, 'avg_step': avg_step,
            'total_exchanges': unique_swaps, 'est_remaining_h': overall_est_h,
            'est_remaining_d': overall_est_d, 'running': running,
        },
        'replicas': replicas, 'temp_visit_counts': temp_visit_counts,
        'output_files': output_files,
    }

    tmp_path = output_path + ".tmp"
    with open(tmp_path, 'w') as f:
        json.dump(result, f, indent=2)
    os.replace(tmp_path, output_path)

    print(f'OK step={avg_step} pct={avg_progress}% running={running} wall={max_wall_time}s swaps={unique_swaps} est_h={overall_est_h}')

if __name__ == '__main__':
    main()
