#!/usr/bin/env python3
"""Transition task generator: sequence -> fully extended PDB + annotations CSV
+ TIGER2 input template.

Runs locally on the backend (no SSH). Reads the task's own
scripts/task_config.json (fields: protein, sequence, annotations) plus any
file the Task Control annotation form dropped at input/annotations.csv, then
writes into the task's local tree:

  output/extended.pdb        fully extended backbone + CB (all-trans peptide)
  output/sequences.csv       annotation CSV in the TIGER2 sequence_annotation
                             format (sequence,label,color)
  output/tiger2_input.conf   NAMD/TIGER2 config template (FILL-IN placeholders)
  output/README.txt          what a TIGER2 task still needs (PSF, params, ...)

Usage:
  python3 generate.py --task-id <id> --local-dir <task base dir>
      [--task-config <task_config.json>]
"""
import argparse
import csv
import json
import math
import os
import sys

AA1_TO_AA3 = {
    "A": "ALA", "R": "ARG", "N": "ASN", "D": "ASP", "C": "CYS",
    "Q": "GLN", "E": "GLU", "G": "GLY", "H": "HIS", "I": "ILE",
    "L": "LEU", "K": "LYS", "M": "MET", "F": "PHE", "P": "PRO",
    "S": "SER", "T": "THR", "W": "TRP", "Y": "TYR", "V": "VAL",
    "U": "SEC", "O": "PYL",
}

# ---------------------------------------------------------------------------
# Internal-coordinate chain builder (extended / all-trans backbone).
# ---------------------------------------------------------------------------
def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def _mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def _dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

def _norm(v):
    n = math.sqrt(_dot(v, v))
    return (0.0, 0.0, 1.0) if n < 1e-12 else (v[0] / n, v[1] / n, v[2] / n)

def place(ref1, ref2, central, dist, angle_deg, dihedral_deg):
    """Place a new atom bonded to `central`.

    Uses the internal-coordinate frame defined by ref1 -> ref2 -> central:
    angle_deg is the angle ref2-central-new; dihedral_deg is the dihedral
    ref1-ref2-central-new (IUPAC convention).
    """
    u = _norm(_sub(ref2, ref1))
    v = _norm(_sub(central, ref2))
    n = _cross(u, v)
    if _dot(n, n) < 1e-12:
        n = (0.0, 0.0, 1.0)
    n = _norm(n)
    b = _norm(_cross(n, v))
    th = math.radians(angle_deg)
    w = math.radians(dihedral_deg)
    d = (
        -math.cos(th) * v[0] + math.sin(th) * math.cos(w) * b[0] + math.sin(th) * math.sin(w) * n[0],
        -math.cos(th) * v[1] + math.sin(th) * math.cos(w) * b[1] + math.sin(th) * math.sin(w) * n[1],
        -math.cos(th) * v[2] + math.sin(th) * math.cos(w) * b[2] + math.sin(th) * math.sin(w) * n[2],
    )
    return _add(central, _mul(d, dist))

# Extended-conformation dihedrals (degrees) + ideal bond/angle geometry.
PHI_EXT, PSI_EXT, OMEGA = -139.0, 135.0, 180.0
BOND_CA_N, BOND_N_C, BOND_C_CA, BOND_CA_CB, BOND_C_O = 1.458, 1.329, 1.525, 1.534, 1.229
ANGLE_N_CA_C, ANGLE_CA_C_N, ANGLE_C_N_CA, ANGLE_N_CA_CB = 111.2, 116.2, 121.3, 110.4
ANGLE_CA_C_O, ANGLE_C_CA_CB = 120.8, 109.6

def build_extended_chain(sequence):
    """Return list of (resname3, atom_name, (x, y, z)) for an extended chain."""
    residues = []
    aa = [c for c in sequence.strip().upper() if c.isalpha()]
    if not aa:
        raise ValueError("sequence is empty")

    # Seed the first residue along +x.
    n1 = (0.0, 0.0, 0.0)
    ca1 = (BOND_CA_N, 0.0, 0.0)
    th = math.radians(180.0 - ANGLE_N_CA_C)
    c1 = _add(ca1, (BOND_C_CA * math.cos(th), BOND_C_CA * math.sin(th), 0.0))

    def atoms_for(resname3, n, ca, c, o, cb):
        out = []
        for name, coord in (("N", n), ("CA", ca), ("C", c), ("O", o)):
            out.append((resname3, name, coord))
        if resname3 != "GLY":
            out.append((resname3, "CB", cb))
        return out

    # Residue 1: N1, CA1, C1 already seeded; derive O1 and CB1.
    o1 = place(n1, ca1, c1, BOND_C_O, ANGLE_CA_C_O, 180.0)
    cb1 = place(c1, n1, ca1, BOND_CA_CB, ANGLE_N_CA_CB, -122.5)
    residues.append(atoms_for(AA1_TO_AA3[aa[0]], n1, ca1, c1, o1, cb1))

    n_prev, ca_prev, c_prev = n1, ca1, c1
    for letter in aa[1:]:
        n_cur = place(n_prev, ca_prev, c_prev, BOND_N_C, ANGLE_CA_C_N, PSI_EXT)
        ca_cur = place(ca_prev, c_prev, n_cur, BOND_CA_N, ANGLE_C_N_CA, OMEGA)
        c_cur = place(c_prev, n_cur, ca_cur, BOND_C_CA, ANGLE_N_CA_C, PHI_EXT)
        o_cur = place(n_cur, ca_cur, c_cur, BOND_C_O, ANGLE_CA_C_O, 180.0)
        cb_cur = place(c_cur, n_cur, ca_cur, BOND_CA_CB, ANGLE_N_CA_CB, -122.5)
        residues.append(atoms_for(AA1_TO_AA3[letter], n_cur, ca_cur, c_cur, o_cur, cb_cur))
        n_prev, ca_prev, c_prev = n_cur, ca_cur, c_cur
    return residues

# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------
def write_pdb(residues, path):
    lines = []
    serial = 1
    for i, resatoms in enumerate(residues, start=1):
        for resname3, atom, (x, y, z) in resatoms:
            element = atom[0] if atom[0] != "C" else "C"
            lines.append(
                "ATOM  %5d %-4s%1s%-4s%1s%4d    %8.3f%8.3f%8.3f%6.2f%6.2f          %2s  \n"
                % (serial, atom, " ", resname3, "A", i, x, y, z, 1.00, 0.00, element)
            )
            serial += 1
    lines.append("TER\n")
    lines.append("END\n")
    with open(path, "w") as f:
        f.writelines(lines)
    return serial - 1

def write_sequences_csv(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sequence", "label", "color"])
        w.writeheader()
        for r in rows:
            w.writerow({"sequence": r.get("sequence", ""), "label": r.get("label", ""), "color": r.get("color", "")})

def write_tiger2_conf(path, protein, sequence):
    conf = """# NAMD/TIGER2 replica-exchange input template.
# FILL-IN the marked fields before use (force field, PSF, parameter files,
# thermostat references). This file was generated by the seq_to_pdb
# transition task from:
#   protein : %(protein)s
#   length  : %(length)d residues
structure    FILL-IN:build/%(protein_safe)s.psf
coordinates  FILL-IN:build/%(protein_safe)s_extended.pdb
parameters   FILL-IN:par_all36_prot.prm
parameters   FILL-IN:par_all36_cmap.prm
temperature  FILL-IN:310.0
timestep     2.0
switching    on
switchdist   10.0
cutoff       12.0
pairlistdist 14.0
exclude      scaled1-4
1-4scaling   1.0

# --- Generalized Born implicit solvent (implicit-only TIGER2 stage) ---
gbis         on
soluteDielectric 1.0
solventDielectric 80.0
alphaCutoff  12.0

# --- Thermostat ---
langevin          on
langevinTemp      FILL-IN:310.0
langevinDamping   1.0
langevinHydrogen  off

# --- Replica exchange (TIGER2) ---
replicas           FILL-IN:4
replicaBasisTemp   FILL-IN:310.0
replicaTempLow     FILL-IN:300.0
replicaTempHigh    FILL-IN:400.0
replicaUseTemps    on
replicaBasisScale  1.0

run FILL-IN:total-steps
"""
    with open(path, "w") as f:
        f.write(conf % {"protein": protein, "length": len(sequence), "protein_safe": (protein or "protein").replace(" ", "_")})

def write_readme(path, files):
    with open(path, "w") as f:
        f.write("Generated by the seq_to_pdb transition task.\n\n")
        f.write("Output files:\n")
        for name in files:
            f.write("  output/%s\n" % name)
        f.write("\nTIGER2 task still needs (place into the tiger2 task's input/):\n")
        f.write("  - extended.pdb              structure coordinates\n")
        f.write("  - sequences.csv             annotation map (viewer legend)\n")
        f.write("  - tiger2_input.conf         fill in the FILL-IN fields\n")
        f.write("  - <protein>.psf             build with psfgen (CHARMM force field)\n")
        f.write("  - parameter files (par_all36_*.prm, toppar, ...)\n")

# ---------------------------------------------------------------------------
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

    protein = str(config.get("protein", "") or "").strip()
    sequence = str(config.get("sequence", "") or "").strip()
    annotations = config.get("annotations") or []

    input_dir = os.path.join(args.local_dir, "input")
    output_dir = os.path.join(args.local_dir, "output")
    for d in (input_dir, output_dir):
        os.makedirs(d, exist_ok=True)

    # Annotation rows: prefer a CSV already written by the Task Control form,
    # otherwise fall back to the config array.
    rows = []
    csv_path = os.path.join(input_dir, "annotations.csv")
    if os.path.exists(csv_path):
        with open(csv_path, newline="") as f:
            rows = list(csv.DictReader(f))
    elif annotations:
        rows = list(annotations)

    generated = []
    if not sequence:
        raise SystemExit(json.dumps({"ok": False, "error": "No sequence set; save the annotation form first (config.sequence)"}))
    try:
        residues = build_extended_chain(sequence)
    except KeyError as e:
        raise SystemExit(json.dumps({"ok": False, "error": "Unknown amino-acid letter in sequence: %s" % e}))
    except ValueError as e:
        raise SystemExit(json.dumps({"ok": False, "error": str(e)}))

    natoms = write_pdb(residues, os.path.join(output_dir, "extended.pdb"))
    write_sequences_csv(rows, os.path.join(output_dir, "sequences.csv"))
    if rows:
        write_sequences_csv(rows, os.path.join(input_dir, "annotations.csv"))
    write_tiger2_conf(os.path.join(output_dir, "tiger2_input.conf"), protein, sequence)
    write_readme(os.path.join(output_dir, "README.txt"), ["extended.pdb", "sequences.csv", "tiger2_input.conf", "README.txt"])

    print(json.dumps({
        "ok": True,
        "files": ["output/extended.pdb", "output/sequences.csv", "output/tiger2_input.conf", "output/README.txt"],
        "atoms": natoms,
        "residues": len(residues),
        "sequence": sequence,
        "annotations": len(rows),
    }))

if __name__ == "__main__":
    main()
