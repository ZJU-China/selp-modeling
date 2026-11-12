#!/usr/bin/env python3
"""Convert GROMACS CG samples' XTC+GRO into PDB + per-sample DCDs for NGL.

The task's pulled output files live at <local_dir>/output/<sample>/ (relax.xtc
+ relax.gro). Every sample with both files is converted, one DCD per sample
under a stable replica index (sorted sample name order), so multiple
simulations (e.g. the shear planes / strains, or a future tensile set) are
shown separately in the viewer. Protein beads are everything that is not CG
water or ions (the Martini GRO uses W/WF for water and NA/CL for ions). Writes:

  <local_dir>/cache/trajectory/topology.pdb             structure (protein beads)
  <local_dir>/cache/trajectory/replica_{i}.dcd          full protein-bead trajectory
  <local_dir>/cache/trajectory/last100/replica_{i}.dcd  trailing <=100 frames
  <local_dir>/cache/trajectory/preview/replica_{i}.dcd  downsampled preview

With --sample given, only that sample is converted (still as replica_0), which
keeps the single-sample workflow / manual re-runs working. --max-samples caps
the number of converted samples (default: all) to bound cache disk usage.

Prints a single JSON status line on stdout:
  {ok, pdbSize, frames, atoms, samples, dcdSizes, last100Sizes, last100Frames,
   previewSizes, previewFrames, error}
Legacy scalar fields (dcdSize, sample, last100Size, previewSize) are kept for
backward compatibility with the sync loop.

Requires MDAnalysis (conda env igem2026). Invoked by the tasktype's trajectory
route after the output pull.
"""
import argparse
import json
import os

try:
    from MDAnalysis.coordinates.DCD import DCDWriter
except ImportError:
    DCDWriter = None


def convert_sample(args, sample, output_dir, cache_dir, replica, pdb_path):
    """Convert one sample into replica_{replica}.dcd (+ preview/last100).

    Returns a dict of per-replica stats, or None on failure (after reporting).
    topology.pdb is (re)written here because the protein bead set is identical
    across samples and the first replica's first frame is a fine structure.
    """
    import MDAnalysis as mda

    xtc = os.path.join(output_dir, sample, "relax.xtc")
    gro = os.path.join(output_dir, sample, "relax.gro")

    # The GRO names water residues W/WF and ions ION, everything else is protein
    # CG beads (Martini: BB/SC* backbone and sidechain beads).
    sel = "not resname W WF ION"
    u = mda.Universe(gro, xtc)
    prot = u.select_atoms(sel)
    if prot.n_atoms == 0:
        print(json.dumps({"ok": False, "error": f"sample {sample}: selection {sel!r} matched 0 atoms"}))
        return None

    # The XTC stores PBC-wrapped coordinates: between frames atoms jump across
    # the box boundary, which the viewer renders as straight lines spanning the
    # structure. The aggregate can be larger than the box, so a per-atom
    # "no jump" unwrap is used: each frame each atom is placed at the previous
    # frame's position plus the minimum-image displacement. The first frame is
    # kept as-is. Result: every atom's motion between frames is continuous and
    # stays below half a box.
    from MDAnalysis.lib.distances import minimize_vectors

    indices = prot.indices
    box = u.dimensions
    n_frames = len(u.trajectory)

    dcd_path = os.path.join(cache_dir, f"replica_{replica}.dcd")
    last100_path = os.path.join(cache_dir, "last100", f"replica_{replica}.dcd")
    preview_path = os.path.join(cache_dir, "preview", f"replica_{replica}.dcd")

    # Structure from the first frame (raw, PBC-wrapped).
    u.trajectory[0]
    prot.write(pdb_path)

    tail_start = max(0, n_frames - args.tail_frames)
    step = max(1, n_frames // args.preview_frames)
    last100_frames = n_frames - tail_start
    preview_frames = len(range(0, n_frames, step))

    prev = None
    with DCDWriter(dcd_path, prot.n_atoms) as w_full, \
         DCDWriter(last100_path, prot.n_atoms) as w_tail, \
         DCDWriter(preview_path, prot.n_atoms) as w_prev:
        for i, ts in enumerate(u.trajectory):
            cur = ts.positions.copy()
            if prev is None:
                unwrapped = cur[indices]
            else:
                delta = minimize_vectors(cur[indices] - prev, box)
                unwrapped = prev + delta
            prev = unwrapped.copy()
            ts.positions[indices] = unwrapped
            w_full.write(prot)
            if i >= tail_start:
                w_tail.write(prot)
            if i % step == 0:
                w_prev.write(prot)

    return {
        "dcdSize": os.path.getsize(dcd_path),
        "last100Size": os.path.getsize(last100_path),
        "last100Frames": last100_frames,
        "previewSize": os.path.getsize(preview_path),
        "previewFrames": preview_frames,
        "frames": n_frames,
        "atoms": prot.n_atoms,
    }


def main():
    p = argparse.ArgumentParser(description="GROMACS CG XTC -> PDB/DCD conversion")
    p.add_argument("task_id")
    p.add_argument("--local-dir", required=True)
    p.add_argument("--sample", default=None)
    p.add_argument("--max-samples", type=int, default=None)
    p.add_argument("--preview-frames", type=int, default=100)
    p.add_argument("--tail-frames", type=int, default=100)
    args = p.parse_args()

    try:
        import MDAnalysis
    except ImportError as e:
        print(json.dumps({"ok": False, "error": f"MDAnalysis unavailable: {e}"}))
        return

    output_dir = os.path.join(args.local_dir, "output")
    cache_dir = os.path.join(args.local_dir, "cache", "trajectory")

    if not os.path.isdir(output_dir):
        print(json.dumps({"ok": False, "error": f"no output dir at {output_dir}"}))
        return

    samples = sorted(d for d in os.listdir(output_dir)
                     if os.path.isdir(os.path.join(output_dir, d)))
    if args.sample:
        samples = [s for s in samples if s == args.sample]
    elif args.max_samples:
        samples = samples[:args.max_samples]

    # Only samples that actually have both files can be converted.
    ready = [s for s in samples
             if os.path.exists(os.path.join(output_dir, s, "relax.xtc"))
             and os.path.exists(os.path.join(output_dir, s, "relax.gro"))]
    if not ready:
        print(json.dumps({"ok": False,
                          "error": "no sample with relax.xtc + relax.gro under output/"}))
        return

    last100_dir = os.path.join(cache_dir, "last100")
    preview_dir = os.path.join(cache_dir, "preview")
    for d in (cache_dir, last100_dir, preview_dir):
        os.makedirs(d, exist_ok=True)

    pdb_path = os.path.join(cache_dir, "topology.pdb")

    samples_out = []
    dcd_sizes = []
    last100_sizes = []
    last100_frames = []
    preview_sizes = []
    preview_frames = []
    frames = []
    atoms = []

    for replica, sample in enumerate(ready):
        stats = convert_sample(args, sample, output_dir, cache_dir, replica, pdb_path)
        if stats is None:
            print(json.dumps({"ok": False, "error": f"conversion failed for {sample}"}))
            return
        samples_out.append(sample)
        dcd_sizes.append(stats["dcdSize"])
        last100_sizes.append(stats["last100Size"])
        last100_frames.append(stats["last100Frames"])
        preview_sizes.append(stats["previewSize"])
        preview_frames.append(stats["previewFrames"])
        frames.append(stats["frames"])
        atoms.append(stats["atoms"])

    # Sidecar so the sync loop's fast path (no re-conversion) can still report
    # the real sample names / frame counts without re-reading the DCDs.
    with open(os.path.join(cache_dir, "meta.json"), "w") as f:
        json.dump({
            "samples": samples_out,
            "previewFrames": preview_frames,
            "last100Frames": last100_frames,
        }, f)

    print(json.dumps({
        "ok": True,
        "pdbSize": os.path.getsize(pdb_path),
        "frames": frames,
        "atoms": atoms,
        "samples": samples_out,
        "dcdSizes": dcd_sizes,
        "last100Sizes": last100_sizes,
        "last100Frames": last100_frames,
        "previewSizes": preview_sizes,
        "previewFrames": preview_frames,
        # Backward-compatible scalar summaries (first replica).
        "dcdSize": dcd_sizes[0],
        "sample": samples_out[0],
        "last100Size": last100_sizes[0],
        "previewSize": preview_sizes[0],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
