"""Crosslink distance analysis for the CG network.

Reads the task's network.json (+ optional crosslink_pairs.tsv) to resolve each
crosslink's two global bead indices, then measures the unwrapped trajectory
DCDs to get per-link distances (A) on every frame. Crosslinks join two beads on
different chains, so this tracks how the inter-chain network stretches under
deformation. Writes:

  crosslink.dat          per-frame aggregate: mean / min / max over links
                         # replica step mean(A) min(A) max(A)
  crosslink_table.tsv    per-link stats over the run (first row a # header):
                         # chain_a site_a chain_b site_b ref(A) mean(A) min(A) max(A) std(A)

Pure helpers (parse/geometry) are testable without MDAnalysis.
"""
import os

import numpy as np

from lib.analysis import paths, writers
from lib.analysis.structure import frame_steps, resolve_chain_layout


def parse_network(path):
    """Resolve network.json into {n_chains, beads_per_chain, links}.

    `links` is a list of (i_a, i_b) 0-based global bead indices, re-derived
    from chain/site (1-based) to be robust against changing atom numbering:
    i = (chain - 1) * beads_per_chain + (site - 1).
    """
    with open(path) as f:
        import json
        net = json.load(f)
    n_chains = int(net.get("n_chains") or 0)
    bpc = int(net.get("beads_per_chain") or 0)
    links = []
    for edge in net.get("edges") or []:
        chain_a = int(edge.get("chain_a") or 0)
        chain_b = int(edge.get("chain_b") or 0)
        site_a = int(edge.get("site_a") or 0)
        site_b = int(edge.get("site_b") or 0)
        if not (bpc and chain_a and chain_b and site_a and site_b):
            continue
        links.append(((chain_a - 1) * bpc + (site_a - 1),
                      (chain_b - 1) * bpc + (site_b - 1)))
    return {"n_chains": n_chains, "beads_per_chain": bpc, "links": links,
            "n_links": len(links)}


def crosslink_distances(pos, links):
    """Euclidean distances on the (unwrapped) positions for each link, in A."""
    if not links:
        return np.zeros(0)
    return np.linalg.norm(pos[np.array(links)[:, 0]] - pos[np.array(links)[:, 1]], axis=1)


def analyze(task_dir, cfg):
    """Run the network module. Returns {ok, links, replicas, error} and writes
    crosslink.dat + crosslink_table.tsv under cache/analysis."""
    out = paths.output_dir(task_dir)
    traj = paths.trajectory_dir(task_dir)
    analysis = paths.analysis_dir(task_dir)
    os.makedirs(analysis, exist_ok=True)

    net_path = paths.network_json_path(task_dir)
    if not net_path:
        return {"ok": False, "error": "network.json not found under task input/"}

    try:
        net = parse_network(net_path)
    except Exception as e:
        return {"ok": False, "error": f"network.json unreadable: {e}"}
    if not net["links"]:
        return {"ok": False, "error": "network.json has no usable edges"}

    dcds = paths.discover_dcds(traj)
    if not dcds:
        return {"ok": False, "error": "no replica_*.dcd under cache/trajectory"}

    topo = paths.topology_path(traj)
    samples = paths.discover_samples(out)
    ready = [s for s in samples if paths.xtc_path(out, s) and paths.gro_path(out, s)]
    dt_fs = cfg.get("timestepFs") or 20
    spc = cfg.get("stepsPerCycle") or 500000

    try:
        from MDAnalysis import Universe
    except ImportError as e:
        return {"ok": False, "error": f"MDAnalysis unavailable: {e}"}

    dat_rows = []
    link_stats = None
    error = None
    replicas = 0
    n_links = len(net["links"])

    for replica, dcd in enumerate(dcds):
        try:
            u = Universe(topo, dcd)
        except Exception as e:
            error = error or f"replica {replica}: {e}"
            continue
        n_atoms = u.atoms.n_atoms
        n_chains, bpc = resolve_chain_layout(n_atoms, net)
        if bpc != net["beads_per_chain"] or n_chains != net["n_chains"]:
            error = error or f"replica {replica}: trajectory size {n_atoms} does not match network {net['n_chains']}x{net['beads_per_chain']}"
            continue

        n_frames = len(u.trajectory)
        sample = ready[replica] if replica < len(ready) else None
        steps = frame_steps(out, sample, n_frames, dt_fs, spc)

        per_frame = []
        frames_seen = 0
        for frame, ts in enumerate(u.trajectory):
            dist = crosslink_distances(ts.positions.copy(), net["links"])
            per_frame.append(dist)
            step = steps[frame] if frame < len(steps) else frame * spc
            if step <= 0:
                continue
            frames_seen += 1
            dat_rows.append((replica, step,
                             round(float(dist.mean()), 4),
                             round(float(dist.min()), 4),
                             round(float(dist.max()), 4)))

        if per_frame:
            mat = np.array(per_frame)  # (frames, n_links) A
            ref = mat[0]
            row = {"ref": ref,
                   "mean": mat.mean(axis=0),
                   "min": mat.min(axis=0),
                   "max": mat.max(axis=0),
                   "std": mat.std(axis=0, ddof=1) if mat.shape[0] > 1 else np.zeros(n_links)}
            if link_stats is None:
                link_stats = row
            else:
                link_stats["ref"] = np.minimum(link_stats["ref"], row["ref"])
            del per_frame
        replicas += 1

    writers.write_dat(os.path.join(analysis, "crosslink.dat"),
                      "replica step mean(A) min(A) max(A)", dat_rows)

    tsv_rows = []
    if link_stats is not None:
        tsv_rows.append(["# chain_a", "site_a", "chain_b", "site_b",
                         "ref(A)", "mean(A)", "min(A)", "max(A)", "std(A)"])
        for i, (i_a, i_b) in enumerate(net["links"]):
            chain_a = i_a // net["beads_per_chain"] + 1
            site_a = i_a % net["beads_per_chain"] + 1
            chain_b = i_b // net["beads_per_chain"] + 1
            site_b = i_b % net["beads_per_chain"] + 1
            tsv_rows.append([
                chain_a, site_a, chain_b, site_b,
                round(float(link_stats["ref"][i]), 4),
                round(float(link_stats["mean"][i]), 4),
                round(float(link_stats["min"][i]), 4),
                round(float(link_stats["max"][i]), 4),
                round(float(link_stats["std"][i]), 4),
            ])
    writers.write_tsv(os.path.join(analysis, "crosslink_table.tsv"), tsv_rows)

    return {"ok": bool(dat_rows), "replicas": replicas, "links": n_links,
            "rows": len(dat_rows), "error": error}