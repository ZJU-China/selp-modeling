#!/usr/bin/env python3
"""analyze.py - Compute Rg, E2E, RMSD from cached DCD trajectories.
Usage: python3 analyze.py <taskId>
Reads:  backend/tasks/<taskId>/cache/trajectory/ (topology.pdb, topology.psf, replica_*.dcd)
Writes: backend/tasks/<taskId>/cache/analysis/    (rg.dat, e2e.dat, rmsd.dat, ss.dat, ...)
The frame->step axis uses stepsPerCycle from the task's task_config.json when
present (default 15000).
"""
import sys, os, json, glob
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_BASE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "tasks"))

def load_steps_per_cycle(task_dir):
    path = os.path.join(task_dir, "scripts", "task_config.json")
    try:
        with open(path) as f:
            d = (json.load(f).get("defaults") or {}).get("stepsPerCycle")
        return int(d) if d else 15000
    except (OSError, ValueError, TypeError):
        return 15000

def main():
    task_id = sys.argv[1] if len(sys.argv) > 1 else "tiger2_zju"
    task_dir = os.path.join(TASKS_BASE, task_id)
    steps_per_cycle = load_steps_per_cycle(task_dir)
    traj_dir = os.path.join(task_dir, "cache", "trajectory")
    analysis_dir = os.path.join(task_dir, "cache", "analysis")
    os.makedirs(analysis_dir, exist_ok=True)

    # Fallback to input/ for topology files
    input_dir = os.path.join(task_dir, "input")

    psf = os.path.join(traj_dir, "topology.psf")
    pdb = os.path.join(traj_dir, "topology.pdb")
    if not os.path.exists(psf) and not os.path.exists(pdb):
        input_psf = os.path.join(input_dir, "topology.psf")
        input_pdb = os.path.join(input_dir, "topology.pdb")
        psf = input_psf if os.path.exists(input_psf) else None
        pdb = input_pdb if os.path.exists(input_pdb) else None
    if (not psf or not os.path.exists(psf)) and (not pdb or not os.path.exists(pdb)):
        print(f"No topology found in {traj_dir} or {input_dir}")
        return False

    topo = psf if psf and os.path.exists(psf) else pdb

    dcds = sorted(glob.glob(os.path.join(traj_dir, "replica_*.dcd")))
    if not dcds:
        print(f"No DCD files found in {traj_dir}")
        return False

    print(f"Topology: {topo}")
    print(f"DCDs: {[os.path.basename(d) for d in dcds]}")

    import warnings
    warnings.filterwarnings("ignore")
    from MDAnalysis import Universe
    from MDAnalysis.analysis import rms

    all_rg = []
    all_e2e = []
    all_rmsd = []
    all_ss = []

    for dcd_path in dcds:
        rep = int(os.path.basename(dcd_path).replace("replica_", "").replace(".dcd", ""))
        try:
            u = Universe(topo, dcd_path)
            protein = u.select_atoms("protein")
            ca = u.select_atoms("name CA")
            ref_coords_ca = ca.positions.copy() if ca.n_atoms > 0 else None

            # Per-residue secondary structure estimate based on phi/psi
            # Extract residue-level features for coarse SS estimate
            n_res = protein.n_residues if hasattr(protein, 'n_residues') else 0

            for ts in u.trajectory:
                frame = ts.frame
                step = frame * steps_per_cycle

                rg = protein.radius_of_gyration() / 10.0
                all_rg.append((rep, step, round(rg, 4)))

                if ca.n_atoms >= 2:
                    e2e = np.linalg.norm(ca.positions[-1] - ca.positions[0]) / 10.0
                else:
                    e2e = np.linalg.norm(protein.positions[-1] - protein.positions[0]) / 10.0
                all_e2e.append((rep, step, round(e2e, 4)))

                if ca.n_atoms > 0 and ref_coords_ca is not None:
                    rmsd_val = rms.rmsd(ca.positions, ref_coords_ca, superposition=True)
                    all_rmsd.append((rep, step, round(rmsd_val / 10.0, 4)))
                else:
                    all_rmsd.append((rep, step, 0))

                # Simple SS estimate based on CA distance matrix
                if n_res > 2:
                    helix_count = 0
                    sheet_count = 0
                    coil_count = n_res
                    # Estimate: adjacent CA distances
                    ca_pos = ca.positions if ca.n_atoms > 0 else protein.positions
                    for ri in range(min(n_res, len(ca_pos) - 1)):
                        d = np.linalg.norm(ca_pos[ri] - ca_pos[min(ri+1, len(ca_pos)-1)])
                        if 1.4 < d < 1.6:
                            helix_count += 1
                        elif 1.2 < d < 1.5:
                            sheet_count += 1
                    h_pct = round(100.0 * helix_count / n_res, 1)
                    s_pct = round(100.0 * sheet_count / n_res, 1)
                    c_pct = round(100.0 * (n_res - helix_count - sheet_count) / n_res, 1)
                    all_ss.append((rep, step, h_pct, s_pct, c_pct))

            print(f"Replica {rep}: {u.trajectory.n_frames} frames, {len(all_rg)} points")
        except Exception as e:
            print(f"Replica {rep} error: {e}")

    if not all_rg:
        print("No data collected")
        return False

    # Write rg.dat
    with open(os.path.join(analysis_dir, "rg.dat"), "w") as f:
        f.write("# replica step rg(nm)\n")
        for rep, step, rg in all_rg:
            f.write(f"{rep}\t{step}\t{rg}\n")
    print(f"rg.dat: {len(all_rg)} points")

    # Write e2e.dat
    with open(os.path.join(analysis_dir, "e2e.dat"), "w") as f:
        f.write("# replica step e2e(nm)\n")
        for rep, step, e2e in all_e2e:
            f.write(f"{rep}\t{step}\t{e2e}\n")
    print(f"e2e.dat: {len(all_e2e)} points")

    # Write rmsd.dat
    with open(os.path.join(analysis_dir, "rmsd.dat"), "w") as f:
        f.write("# replica step rmsd(nm)\n")
        for rep, step, rmsd in all_rmsd:
            f.write(f"{rep}\t{step}\t{rmsd}\n")
    print(f"rmsd.dat: {len(all_rmsd)} points")

    # Write ss.dat
    if all_ss:
        with open(os.path.join(analysis_dir, "ss.dat"), "w") as f:
            f.write("# replica step helix sheet coil\n")
            for rep, step, h, s, c in all_ss:
                f.write(f"{rep}\t{step}\t{h}\t{s}\t{c}\n")
        print(f"ss.dat: {len(all_ss)} points")
    else:
        with open(os.path.join(analysis_dir, "ss.dat"), "w") as f:
            f.write("# step helix sheet coil\n")
        print("ss.dat: empty")

    # Clustering (Rg + E2E)
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    coords = np.array([[rg, e2e] for (_, _, rg), (_, _, e2e) in zip(all_rg, all_e2e)])
    print(f"Clustering {len(coords)} points...")

    best_k, best_score = 2, -1
    for k in range(2, min(8, len(coords))):
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(coords)
        score = silhouette_score(coords, labels)
        if score > best_score:
            best_k, best_score = k, score

    km = KMeans(n_clusters=best_k, n_init=10, random_state=42)
    labels = km.fit_predict(coords)

    colors = ["#007aff", "#ff9500", "#34c759", "#af52de", "#ff3b30", "#5ac8fa", "#ff2d55"]
    labels_name = ["Extended", "Semi-compact", "Compact", "Folded", "Misfolded", "Loose", "Dense"]

    clusters = []
    for cid in range(best_k):
        mask = labels == cid
        pts = coords[mask]
        pop = round(100.0 * mask.sum() / len(labels), 1)
        clusters.append({
            "id": cid, "label": "", "color": colors[cid % len(colors)],
            "rgCenter": round(float(pts[:, 0].mean()), 3),
            "e2eCenter": round(float(pts[:, 1].mean()), 3),
            "population": pop,
        })

    clusters.sort(key=lambda c: c["rgCenter"], reverse=True)
    for i, c in enumerate(clusters):
        c["id"] = i
        c["label"] = labels_name[i % len(labels_name)]

    with open(os.path.join(analysis_dir, "cluster_results.json"), "w") as f:
        json.dump({"clusters": clusters, "points": None}, f)

    scatter_points = []
    for i, (rg, e2e) in enumerate(coords):
        cid = int(labels[i])
        scatter_points.append({
            "rg": round(float(rg), 4),
            "e2e": round(float(e2e), 4),
            "cluster": cid,
            "color": colors[cid % len(colors)],
        })
    with open(os.path.join(analysis_dir, "cluster_scatter.json"), "w") as f:
        json.dump({"clusters": clusters, "points": scatter_points}, f)

    print(f"Done: {best_k} clusters, silhouette={best_score:.3f}")
    return True

if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
