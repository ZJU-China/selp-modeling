"""Structural metrics from the cached protein-bead trajectory.

Computes per-replica, per-frame:
  rg.dat           radius of gyration (all protein beads)          [A]
  e2e.dat          end-to-end distance (first bead <-> last bead)  [A]
  rmsd.dat         RMSD vs the first frame (alignment)             [A]
  chain_rg.dat     per-chain Rg aggregated (mean, min, max)        [A]
  box.dat          box dimensions from each sample's relax.gro     [nm]

Frame -> step axis: when the matching relax.xtc is available locally its real
frame times are used (step = round(t_ps * 1000 / dt_fs)); otherwise each frame
counts as one cycle (step = frame * stepsPerCycle), the TIGER2 convention. The
analysis writes the trajectory cache (unwrapped DCDs) — structure.frame_steps
returns the step axis shared by the network module.

MDAnalysis is imported lazily so pure helpers are testable without it.
"""
import os

import numpy as np

from lib.analysis import paths, writers

_UNITS = "(A)"


def _rgyr(pos):
    """Radius of gyration (unweighted, MDA equals-mass convention) in A."""
    com = pos.mean(axis=0)
    return float(np.sqrt(((pos - com) ** 2).sum(axis=1).mean()))


def _e2e(pos):
    return float(np.linalg.norm(pos[-1] - pos[0]))


def _chain_rg_stats(pos, n_chains, beads_per_chain):
    """Per-chain Rg -> (mean, min, max) across chains. Single-chain input
    behaves as one chain (values all equal to the system Rg)."""
    if n_chains <= 1 or beads_per_chain <= 0:
        rg = _rgyr(pos)
        return rg, rg, rg
    rgs = []
    for c in range(n_chains):
        sl = slice(c * beads_per_chain, (c + 1) * beads_per_chain)
        rgs.append(_rgyr(pos[sl]))
    return float(np.mean(rgs)), float(np.min(rgs)), float(np.max(rgs))


def resolve_chain_layout(n_atoms, network):
    """(n_chains, beads_per_chain) from network.json when the topology matches,
    else (1, n_atoms)."""
    n_chains = (network or {}).get("n_chains")
    bpc = (network or {}).get("beads_per_chain")
    if n_chains and bpc and n_atoms == int(n_chains) * int(bpc):
        return int(n_chains), int(bpc)
    return 1, n_atoms


def frame_steps(out_dir, sample, n_frames, dt_fs, steps_per_cycle):
    """Step value per trajectory frame.

    Prefers real frame times from output/<sample>/relax.xtc (returned as a
    list); falls back to frame * stepsPerCycle. Returns None only when
    n_frames is 0.
    """
    if n_frames <= 0:
        return []
    real_times = _xtc_times(out_dir, sample)
    if real_times is not None and len(real_times) == n_frames and dt_fs:
        return [round(t * 1000.0 / dt_fs) for t in real_times]
    return [i * steps_per_cycle for i in range(n_frames)]


def _xtc_times(out_dir, sample):
    """Real per-frame times (ps) from output/<sample>/relax.xtc, or None."""
    if not out_dir or not sample:
        return None
    xtc = paths.xtc_path(out_dir, sample)
    gro = paths.gro_path(out_dir, sample)
    if not xtc or not gro:
        return None
    try:
        from MDAnalysis import Universe
        return Universe(gro, xtc).trajectory.times
    except Exception:
        return None


def _rmsd_vs_ref(pos, ref, superposition):
    from MDAnalysis.analysis import rms
    return float(rms.rmsd(pos, ref, superposition=superposition))


def analyze(task_dir, cfg, network=None):
    """Run the structure module. Returns {ok, replicas, frames, ...} and writes
    rg.dat / e2e.dat / rmsd.dat / chain_rg.dat / box.dat under cache/analysis."""
    out = paths.output_dir(task_dir)
    traj = paths.trajectory_dir(task_dir)
    analysis = paths.analysis_dir(task_dir)
    os.makedirs(analysis, exist_ok=True)

    dcds = paths.discover_dcds(traj)
    if not dcds:
        return {"ok": False, "error": "no replica_*.dcd under cache/trajectory"}

    topo = paths.topology_path(traj)
    samples = paths.discover_samples(out)
    ready = [s for s in samples if paths.xtc_path(out, s) and paths.gro_path(out, s)]

    dt_fs = cfg.get("timestepFs") or 20
    spc = cfg.get("stepsPerCycle") or 500000

    rg_rows, e2e_rows, rmsd_rows, chain_rows, box_rows = [], [], [], [], []
    frames = []
    replicas = 0
    error = None

    try:
        from MDAnalysis import Universe
    except ImportError as e:
        return {"ok": False, "error": f"MDAnalysis unavailable: {e}"}

    for replica, dcd in enumerate(dcds):
        try:
            u = Universe(topo, dcd)
        except Exception as e:
            error = error or f"replica {replica}: {e}"
            continue

        n_atoms = u.atoms.n_atoms
        if n_atoms == 0:
            continue
        n_chains, bpc = resolve_chain_layout(n_atoms, network)
        n_frames = len(u.trajectory)
        sample = ready[replica] if replica < len(ready) else None
        steps = frame_steps(out, sample, n_frames, dt_fs, spc)

        ref = None
        first = True
        for frame, ts in enumerate(u.trajectory):
            pos = ts.positions.copy()
            if first:
                ref = pos.copy()
                first = False
            step = steps[frame] if frame < len(steps) else frame * spc
            if step <= 0:
                continue
            rg = _rgyr(pos)
            rg_rows.append((replica, step, round(rg, 4)))
            e2e_rows.append((replica, step, round(_e2e(pos), 4)))
            try:
                rmsd_rows.append((replica, step, round(_rmsd_vs_ref(pos, ref, superposition=True), 4)))
            except Exception:
                rmsd_rows.append((replica, step, 0.0))
            mean_rg, min_rg, max_rg = _chain_rg_stats(pos, n_chains, bpc)
            chain_rows.append((replica, step, round(mean_rg, 4), round(min_rg, 4), round(max_rg, 4)))

        replicas += 1
        frames.append(n_frames)

        if sample:
            gro = paths.gro_path(out, sample)
            if gro:
                try:
                    dims = Universe(gro).dimensions[:3]
                except Exception:
                    dims = None
                if dims is not None and len(dims) == 3:
                    box_rows.append((replica, 0, round(float(dims[0]), 3),
                                     round(float(dims[1]), 3), round(float(dims[2]), 3)))

    writers.write_dat(os.path.join(analysis, "rg.dat"), f"replica step rg{_UNITS}", rg_rows)
    writers.write_dat(os.path.join(analysis, "e2e.dat"), f"replica step e2e{_UNITS}", e2e_rows)
    writers.write_dat(os.path.join(analysis, "rmsd.dat"), f"replica step rmsd{_UNITS}", rmsd_rows)
    writers.write_dat(os.path.join(analysis, "chain_rg.dat"),
                      f"replica step mean_rg{_UNITS} min_rg{_UNITS} max_rg{_UNITS}", chain_rows)
    writers.write_dat(os.path.join(analysis, "box.dat"),
                      "replica step box_x(nm) box_y(nm) box_z(nm)", box_rows)

    return {
        "ok": bool(rg_rows),
        "replicas": replicas,
        "frames": frames,
        "error": error,
        "rows": len(rg_rows),
    }