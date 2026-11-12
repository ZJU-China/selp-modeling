#!/usr/bin/env python3
"""Transition task generator: TIGER2 output -> GROMACS CG input.

Reads the upstream TIGER2 task's output (the flow-linked predecessor, or the
task config's sourceTaskId) and produces the input files a GROMACS CG run
needs at a user-set temperature:

  output/cg_start.pdb        last frame of the tiger2 trajectory (or, if no
                             trajectory is available, the topology structure)
  output/cg_input.mdp        Martini-style GROMACS mdp at the requested T (K)
  output/README.txt          how the CG inputs map to a gromacs_cg task
  output/from-tiger2/        a copy of the tiger2 task's output files that the
                             CG run will actually consume

Temperature is entered in Celsius (config.temperatureC) and converted to
Kelvin by this script (T[K] = T[C] + 273.15).

The conversion itself is `convert(src_output, output_dir, ...)`, which is
imported and called by `flow_tiger2/main.py` as well: the flow wrapper folds
this step into the TIGER2 step (whose own output is the DCD source), so the
conversion lives here in exactly one place instead of being forked.

Usage:
  python3 generate.py --task-id <id> --local-dir <task base dir>
      [--task-config <task_config.json>]
"""
import argparse
import json
import os
import shutil
import struct

# ---------------------------------------------------------------------------
# Minimal CHARMM/NAMD DCD reader (last frame only).
# ---------------------------------------------------------------------------
def dcd_last_frame(path):
    """Return (xs, ys, zs, natoms, nframes) for the last frame of a DCD file.

    Handles both standard CHARMM DCD (CORD at byte 0) and NAMD 3 DCD
    (4-byte size prefix before CORD).  Coordinate blocks may be individually
    wrapped with block-size markers (X, Y, Z separate) or stored as a single
    contiguous block.
    """
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 300:
        raise ValueError("DCD file too small: %s" % path)

    def _ri(off):
        return struct.unpack_from("<i", data, off)[0]

    # Locate CORD magic.
    if data[:4] == b"CORD":
        hdr_start = 4
    elif data[4:8] == b"CORD":
        hdr_start = 8
    else:
        raise ValueError("DCD header missing CORD magic: %s" % path)

    # Read 80-byte header (20 ints): nset, istart, nsavc, nstep, nfixed, ...
    nset    = _ri(hdr_start)
    istart  = _ri(hdr_start + 4)
    nsavc   = _ri(hdr_start + 8)

    # Scan forward from after header to locate the natoms block [4][natoms][4].
    scan_start = hdr_start + 80
    natoms = None
    frame_start = None
    for i in range(scan_start, min(scan_start + 400, len(data) - 8)):
        if _ri(i) == 4 and _ri(i + 4) > 0 and _ri(i + 4) < 500000 and _ri(i + 8) == 4:
            candidate = _ri(i + 4)
            if natoms is None:
                natoms = candidate
                frame_start = i + 12  # right after the trailing 4

    if natoms is None or natoms <= 0 or frame_start is None:
        raise ValueError("DCD atom count not found: %s" % path)

    # Detect frame layout: either 3 separate [sz][X][sz][sz][Y][sz][sz][Z][sz]
    # blocks, or a single [sz][XYZ][sz] block.
    first_sz = _ri(frame_start)
    if first_sz == natoms * 4:
        # X, Y, Z stored separately with block-size wrappers.
        coord_block = 4 + natoms * 4 + 4       # 26868
        frame_size = coord_block * 3             # 80604
        xyz_offset = frame_start + 4             # skip leading sz
    elif first_sz == natoms * 3 * 4:
        # Single contiguous XYZ block.
        frame_size = 4 + natoms * 3 * 4 + 4
        xyz_offset = frame_start + 4
    else:
        raise ValueError("Unexpected DCD frame block size %d (natoms=%d)" % (first_sz, natoms))

    remaining = len(data) - frame_start
    nframes = max(1, remaining // frame_size)
    last = frame_start + (nframes - 1) * frame_size

    # Extract coordinates from last frame.
    if first_sz == natoms * 4:
        # 3 separate blocks.
        x_off = last + 4
        y_off = x_off + natoms * 4 + 4 + 4   # skip X block + trailing + Y leading sz
        z_off = y_off + natoms * 4 + 4 + 4
        xs = list(struct.unpack_from("<%df" % natoms, data, x_off))
        ys = list(struct.unpack_from("<%df" % natoms, data, y_off))
        zs = list(struct.unpack_from("<%df" % natoms, data, z_off))
    else:
        coords = struct.unpack_from("<%df" % (natoms * 3), data, xyz_offset)
        xs, ys, zs = list(coords[0::3]), list(coords[1::3]), list(coords[2::3])

    return xs, ys, zs, natoms, nframes

# ---------------------------------------------------------------------------
# PDB helpers
# ---------------------------------------------------------------------------
def parse_pdb_atoms(path):
    """Return (serial, name, resname, chain, resseq, element) for ATOM/HETATM."""
    atoms = []
    with open(path) as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")):
                try:
                    atoms.append((
                        int(line[6:11]),
                        line[12:16].strip(),
                        line[17:20].strip(),
                        line[21:22].strip() or "A",
                        int(line[22:26]),
                        line[76:78].strip(),
                    ))
                except ValueError:
                    continue
    return atoms

def write_frame_pdb(atoms, xs, ys, zs, path):
    """Rewrite a PDB with new coordinates (atom count must match)."""
    if len(atoms) != len(xs):
        raise ValueError("frame atom count (%d) != topology atom count (%d)" % (len(xs), len(atoms)))
    lines = []
    for (serial, name, resname, chain, resseq, element), (x, y, z) in zip(atoms, zip(xs, ys, zs)):
        element = (element or (name[0] if name else "C")) or "C"
        lines.append(
            "ATOM  %5d %-4s%1s%-4s%1s%4d    %8.3f%8.3f%8.3f%6.2f%6.2f          %2s  \n"
            % (serial, name, " ", resname, chain, resseq, x, y, z, 1.00, 0.00, element)
        )
    lines.append("TER\nEND\n")
    with open(path, "w") as f:
        f.writelines(lines)

def write_generic_pdb(xs, ys, zs, path):
    """Fallback: coordinate-only PDB (no topology available)."""
    lines = []
    for i, (x, y, z) in enumerate(zip(xs, ys, zs), start=1):
        lines.append(
            "ATOM  %5d  %-3s %3s A%4d    %8.3f%8.3f%8.3f%6.2f%6.2f           C    \n"
            % (i, "CA", "UNK", i, x, y, z, 1.00, 0.00)
        )
    lines.append("TER\nEND\n")
    with open(path, "w") as f:
        f.writelines(lines)

def write_mdp(path, kelvin):
    mdp = """; Martini CG GROMACS input template, generated by tiger2_dcd_to_gromacs_cg_pdb.
; Target temperature: %.2f K (%.2f C)
integrator          = md
dt                  = 0.020   ; ps (Martini 3 default 20 fs)
nsteps              = 5000000 ; 100 ns (adjust)
nstxout-compressed  = 10000   ; every 200 ps
nstlog              = 5000
nstenergy           = 5000
constraints         = none
; Temperature coupling (Berendsen or v-rescale)
tcoupl              = v-rescale
tc-grps             = System
tau-t               = 1.0
ref-t               = %.2f
; Pressure coupling
pcoupl              = berendsen
pcoupltype          = isotropic
tau-p               = 12.0
ref-p               = 1.0
compressibility     = 3e-4
; Nonbonded
cutoff-scheme       = Verlet
rlist               = 1.1
rcoulomb            = 1.1
rvdw                = 1.1
DispCorr            = no
""" % (kelvin, kelvin - 273.15, kelvin)
    with open(path, "w") as f:
        f.write(mdp)

def write_readme(path, items, kelvin, generator="tiger2_dcd_to_gromacs_cg_pdb transition task"):
    with open(path, "w") as f:
        f.write("Generated by the %s.\n\n" % generator)
        f.write("Target temperature: %.2f K (%.2f C)\n\n" % (kelvin, kelvin - 273.15))
        f.write("Output files (input set for a gromacs_cg task):\n")
        for name in items:
            f.write("  output/%s\n" % name)
        f.write("\nUse with the gromacs_cg task type: upload these into the CG task's input,\n")
        f.write("or place them in its flow so the CG task sees them in output/from-tiger2.\n")

# ---------------------------------------------------------------------------
def find_source_output(local_dir, config):
    """Resolve the upstream tiger2 task's base + output dir."""
    siblings = os.path.dirname(os.path.normpath(local_dir))

    def exists_base(task_id):
        return os.path.isdir(os.path.join(siblings, task_id))

    src_id = str(config.get("sourceTaskId") or "").strip()
    if src_id and exists_base(src_id):
        return src_id, os.path.join(siblings, src_id, "output")

    # Fall back to the flow-linked predecessor: input/flow-<prevId>.
    input_dir = os.path.join(local_dir, "input")
    if os.path.isdir(input_dir):
        for name in sorted(os.listdir(input_dir)):
            if name.startswith("flow-"):
                prev_id = name[len("flow-"):]
                return prev_id, os.path.join(siblings, prev_id, "output")
    # Last resort: use the task's own input dir (files uploaded manually).
    return "", input_dir

def convert(src_output, output_dir, temperature_c=37.0, src_id="", snapshot=True,
            generator="tiger2_dcd_to_gromacs_cg_pdb transition task"):
    """Produce the CG input set from a source output directory.

    Shared by two callers, which is why `src_output` is a parameter rather than
    resolved here:

      * the standalone transition task: src_output is the upstream TIGER2
        task's output dir (`find_source_output`), so its raw files are
        snapshotted into output/from-tiger2/;
      * flow_tiger2, which folds this step into the TIGER2 step: src_output
        *is* the task's own output dir, and the DCDs may also sit in its
        cache/trajectory/.

    Returns a result dict; never raises for user-fixable input, so callers can
    report precisely.
    """
    try:
        temperature_c = float(temperature_c)
    except (TypeError, ValueError):
        temperature_c = 37.0
    kelvin = temperature_c + 273.15

    os.makedirs(output_dir, exist_ok=True)

    notes = []
    files = []

    # 1) Snapshot of the tiger2 output actually consumed downstream. When the
    #    source IS the output dir (the flow_tiger2 case) the walk must not
    #    descend into the snapshot it is writing, nor sweep up the CG inputs a
    #    previous run wrote here -- otherwise the conversion copies its own
    #    output into itself on every run.
    snap_dir = os.path.join(output_dir, "from-tiger2")
    if snapshot and os.path.isdir(src_output):
        self_source = os.path.abspath(src_output) == os.path.abspath(output_dir)
        skip = {"from-tiger2", "cg_start.pdb", "cg_input.mdp", "README.txt"} if self_source else set()
        shutil.rmtree(snap_dir, ignore_errors=True)
        os.makedirs(snap_dir, exist_ok=True)
        n_copied = 0
        for root, dirs, fnames in os.walk(src_output):
            if self_source:
                dirs[:] = [d for d in dirs if d not in skip]
            for fn in fnames:
                if fn in skip:
                    continue
                src = os.path.join(root, fn)
                rel = os.path.relpath(src, src_output)
                dst = os.path.join(snap_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    shutil.copy2(src, dst)
                    n_copied += 1
                except OSError:
                    pass
        files.append("from-tiger2/ (%d files from %s)" % (n_copied, src_id or "input"))
    else:
        notes.append("no upstream tiger2 output found (source: %s)" % (src_id or "input"))

    # 2) Locate topology + trajectory. The source output dir, its cache/
    #    trajectory (written by the trajectory viewer's download), and its own
    #    output/ are all in play.
    search_dirs = [src_output]
    for sd in list(search_dirs):
        if sd:
            search_dirs.append(os.path.join(os.path.dirname(sd), "cache", "trajectory"))
            search_dirs.append(os.path.join(os.path.dirname(sd), "output"))

    def find_files(dirs, exts):
        out = []
        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            for root, _dirs, fnames in os.walk(d):
                for fn in fnames:
                    if fn.lower().endswith(exts):
                        out.append(os.path.join(root, fn))
        return out

    topology = None
    for cand in sorted(find_files(search_dirs, (".pdb",))):
        if os.path.basename(cand).lower().startswith("top") or "topology" in os.path.basename(cand).lower():
            topology = cand
            break
    if not topology and find_files(search_dirs, (".pdb",)):
        topology = sorted(find_files(search_dirs, (".pdb",)))[0]
    dcds = sorted(find_files(search_dirs, (".dcd",)))

    # 3) Extract the stable conformation.
    written = None
    if dcds:
        dcd = dcds[0]
        try:
            xs, ys, zs, natoms, nframes = dcd_last_frame(dcd)
            notes.append("extracted last frame (frame %d of %d) from %s" % (nframes, nframes, os.path.basename(dcd)))
            out_pdb = os.path.join(output_dir, "cg_start.pdb")
            if topology:
                try:
                    atoms = parse_pdb_atoms(topology)
                    if len(atoms) == natoms:
                        write_frame_pdb(atoms, xs, ys, zs, out_pdb)
                        written = out_pdb
                        notes.append("rebuilt coordinates onto topology %s" % os.path.basename(topology))
                    else:
                        raise ValueError("count mismatch")
                except ValueError:
                    write_generic_pdb(xs, ys, zs, out_pdb)
                    written = out_pdb
                    notes.append("topology atom count mismatch — wrote coordinate-only PDB")
            else:
                write_generic_pdb(xs, ys, zs, out_pdb)
                written = out_pdb
                notes.append("no topology found — wrote coordinate-only PDB")
        except Exception as e:
            notes.append("DCD read failed: %s" % e)

    if not written and topology:
        shutil.copy2(topology, os.path.join(output_dir, "cg_start.pdb"))
        written = os.path.join(output_dir, "cg_start.pdb")
        notes.append("copied topology structure as cg_start.pdb (stability not confirmed)")
    elif not written:
        notes.append("no trajectory or topology found; only mdp/README generated")

    if written:
        files.append("cg_start.pdb")

    # 4) MDP + README.
    write_mdp(os.path.join(output_dir, "cg_input.mdp"), kelvin)
    files.append("cg_input.mdp")
    write_readme(os.path.join(output_dir, "README.txt"), files, kelvin, generator=generator)
    files.append("README.txt")

    return {
        "ok": True,
        "files": files,
        "temperatureC": temperature_c,
        "temperatureK": round(kelvin, 2),
        "sourceTaskId": src_id or None,
        "notes": notes,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--task-id", required=True)
    p.add_argument("--local-dir", required=True)
    p.add_argument("--task-config", default=None)
    args = p.parse_args()

    config = {}
    if args.task_config:
        try:
            with open(args.task_config) as f:
                config = json.load(f) or {}
        except Exception:
            config = {}

    src_id, src_output = find_source_output(args.local_dir, config)
    output_dir = os.path.join(args.local_dir, "output")
    result = convert(
        src_output,
        output_dir,
        temperature_c=config.get("temperatureC", 37.0),
        src_id=src_id,
        snapshot=True,
    )
    print(json.dumps(result))

if __name__ == "__main__":
    main()
