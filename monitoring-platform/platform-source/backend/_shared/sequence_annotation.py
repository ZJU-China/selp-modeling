"""Residue-level peptide annotation for MD structures.

Standardized workflow
---------------------
1. Task authors drop a CSV at ``<task>/input/sequences.csv`` with a header
   row and one motif per line::

       sequence,label,color
       KLGYIEFYKVEK,SnoopTag,#ff4d4f
       GGGGS,Flexible linker peptide,#52c41a

   - ``sequence``  1-letter amino-acid code of the peptide motif (uppercase).
   - ``label``     display name shown in the viewer legend.
   - ``color``     hex colour used to highlight every occurrence.

2. The backend route ``sequences`` reads the CSV, loads the task's structure
   (``cache/trajectory/topology.pdb``, else the first ``input/*.pdb``) and
   finds *every* occurrence of each motif (contiguous 1-letter match per
   chain). Occurrences are reported as 1-based residue ranges.

3. The frontend MD-trajectory viewer highlights each occurrence with the CSV
   colour, so repeated motifs (e.g. a SnoopTag at both termini, multiple
   flexible linkers) are all annotated, not just the first hit.
"""
import csv
import glob
import os

# PDB/CHARMM 3-letter residue names -> 1-letter code. Covers the common
# protonation / alt-name variants a topology PDB can contain.
AA3 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "HSD": "H", "HSE": "H", "HSP": "H", "HID": "H", "HIE": "H", "HIP": "H",
    "CYX": "C", "CYM": "C", "ASH": "D", "AS4": "D", "GLH": "E",
    "LYN": "K", "TYM": "Y", "SEC": "U", "PYL": "O",
}

CSV_FILENAME = "sequences.csv"
DEFAULT_COLOR = "#ff8c00"

DEFAULT_PALETTE = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4",
    "#42d4f4", "#f032e6", "#bfef45", "#469990", "#dcbeff", "#9a6324",
    "#800000", "#aaffc3", "#808000", "#ffd8b1", "#000075", "#a9a9a9",
]


def _assign_distinct_colors(rows):
    """Ensure every sequence carries a distinct hex color."""
    used = set()
    for row in rows:
        color = (row.get("color") or "").strip()
        if color and color.lower() not in used:
            used.add(color.lower())
            continue
        color = next(
            (c for c in DEFAULT_PALETTE if c.lower() not in used),
            DEFAULT_COLOR,
        )
        used.add(color.lower())
        row["color"] = color
    return rows


def _read_csv(path):
    """Parse a sequences.csv into [{sequence, label, color}], in file order."""
    rows = []
    with open(path, newline="") as f:
        for raw in csv.DictReader(f):
            row = {str(k).strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            seq = row.get("sequence", "").upper()
            if not seq:
                continue
            rows.append({
                "sequence": seq,
                "label": row.get("label") or seq,
                "color": row.get("color") or "",
            })
    return rows


def _parse_pdb_sequences(pdb_path):
    """Parse a topology PDB into per-chain residue records."""
    chains = {}
    order = []
    with open(pdb_path) as f:
        for line in f:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            serial_txt = line[6:11].strip()
            serial = int(serial_txt) if serial_txt.isdigit() else None
            chain = line[21]
            resname = line[17:20].strip()
            try:
                resid = int(line[22:26])
            except ValueError:
                continue
            recs = chains.setdefault(chain, [])
            if recs and recs[-1]["resid"] == resid:
                recs[-1]["end"] = serial if serial is not None else recs[-1]["end"]
            else:
                recs.append({
                    "chain": chain,
                    "resid": resid,
                    "resname": resname,
                    "one": AA3.get(resname, "X"),
                    "start": serial if serial is not None else 0,
                    "end": serial if serial is not None else 0,
                })
                if chain not in order:
                    order.append(chain)
    out = []
    for chain in order:
        recs = chains[chain]
        out.append({
            "chain": chain,
            "seq": "".join(r["one"] for r in recs),
            "residues": recs,
        })
    return out


# Solvent, ions and cryoprotectants are HETATM groups that carry no sequence.
# They must not be concatenated into a residue chain, or the derived sequence
# gains residues that the coordinate builder will later reject.
NON_POLYMER = {
    "HOH", "WAT", "TIP3", "TIP4", "SOL", "DOD",
    "NA", "K", "CL", "BR", "IOD", "MG", "CA", "ZN", "FE", "CU", "MN", "CD",
    "SO4", "PO4", "GOL", "EDO", "DMS", "MPO",
}


def _has_insertion_codes(pdb_path):
    """PDB column 27 is the insertion code. Two residues sharing a resid differ
    only by it, and _parse_pdb_sequences keys on resid alone, so they would be
    merged into one -- silently corrupting the derived sequence. Rare in
    CHARMM/PSF-derived topologies, but worth reporting rather than ignoring."""
    with open(pdb_path) as f:
        for line in f:
            if line.startswith(("ATOM", "HETATM")) and line[26].strip():
                return True
    return False


def derive_sequence(local_task):
    """Reverse a task's structure back to its one-letter input sequence.

    A TIGER2 run set up from a prebuilt topology often has no sequence anywhere
    in its config, scripts or logs -- the PDB is the only surviving record. This
    reads the same structure the viewer loads (``_find_pdb``: cached
    topology.pdb, else input/*.pdb) and reconstructs the per-chain sequence.

    This recovers the *sequence*, not the coordinates: feeding it back into the
    sequence->PDB builder produces a fresh extended chain, not the original
    folded structure. Non-standard residues are reported rather than guessed,
    so an ambiguous sequence is never presented as a clean one.
    """
    pdb_path = _find_pdb(local_task)
    if not pdb_path:
        return {
            "ok": False,
            "error": "no structure found (cache/trajectory/topology.pdb or input/*.pdb)",
        }

    chains = []
    unknown_total = 0
    for c in _parse_pdb_sequences(pdb_path):
        seq = []
        skipped = []
        unknown = []
        for r in c["residues"]:
            if r.get("resname", "") in NON_POLYMER:
                continue
            one = r["one"]
            if one == "X":
                unknown.append({"resid": r["resid"], "resname": r.get("resname", "?")})
            seq.append(one)
        unknown_total += len(unknown)
        chains.append({
            "chain": c["chain"],
            "sequence": "".join(seq),
            "residues": len(seq),
            "unknown": unknown,
            "skippedNonPolymer": len(skipped),
        })

    result = {
        "ok": True,
        "pdb": os.path.basename(pdb_path),
        "pdbPath": pdb_path,
        "chains": chains,
        "totalResidues": sum(c["residues"] for c in chains),
        "unknownResidues": unknown_total,
    }

    notes = []
    if len(chains) > 1:
        notes.append(
            "Structure has %d chains (%s); the coordinate builder produces a "
            "single chain, so pick one." % (len(chains), ", ".join(c["chain"] for c in chains))
        )
    if unknown_total:
        names = sorted({u["resname"] for c in chains for u in c["unknown"]})
        notes.append(
            "%d residue(s) are not standard amino acids (%s). They are returned "
            "as X and cannot be rebuilt as-is." % (unknown_total, ", ".join(names))
        )
    if _has_insertion_codes(pdb_path):
        notes.append(
            "Structure uses PDB insertion codes, so residues sharing a number "
            "are merged; the derived sequence may be shorter than the real one."
        )
    if notes:
        result["notes"] = notes

    return result


def _find_all(seq, peptide):
    """Start indices of every (incl. overlapping) occurrence of peptide in seq."""
    hits = []
    start = 0
    while True:
        i = seq.find(peptide, start)
        if i == -1:
            break
        hits.append(i)
        start = i + 1
    return hits


def _find_pdb(local_task):
    cached = os.path.join(local_task, "cache", "trajectory", "topology.pdb")
    if os.path.isfile(cached):
        return cached
    for p in sorted(glob.glob(os.path.join(local_task, "input", "*.pdb"))):
        return p
    return None


def compute(local_task, cfg):
    """Compute residue annotations for a task. Pure stdlib, local-only."""
    input_dir = os.path.join(local_task, "input")
    csv_path = os.path.join(input_dir, CSV_FILENAME)
    if not os.path.isfile(csv_path):
        return {"ok": True, "csv": None, "annotations": [],
                "message": f"no {CSV_FILENAME} in {input_dir}"}

    rows = _read_csv(csv_path)
    rows = _assign_distinct_colors(rows)
    if not rows:
        return {"ok": True, "csv": os.path.basename(csv_path), "annotations": [],
                "message": f"{CSV_FILENAME} has no rows"}

    pdb_path = _find_pdb(local_task)
    if not pdb_path:
        return {"ok": False, "annotations": [],
                "error": "no structure found (cache/trajectory/topology.pdb or input/*.pdb)"}

    chains = _parse_pdb_sequences(pdb_path)
    total_residues = sum(len(c["residues"]) for c in chains)

    annotations = []
    for row in rows:
        peptide = row["sequence"].upper()
        occurrences = []
        for chain in chains:
            for i in _find_all(chain["seq"], peptide):
                seg = chain["residues"][i:i + len(peptide)]
                occurrences.append({
                    "chain": chain["chain"],
                    "start": seg[0]["resid"],
                    "end": seg[-1]["resid"],
                    "atomStart": seg[0]["start"],
                    "atomEnd": seg[-1]["end"],
                })
        annotations.append({
            "sequence": row["sequence"],
            "label": row["label"],
            "color": row["color"],
            "occurrences": occurrences,
        })

    return {
        "ok": True,
        "csv": os.path.basename(csv_path),
        "pdb": os.path.basename(pdb_path),
        "chains": [c["chain"] for c in chains],
        "totalResidues": total_residues,
        "annotations": annotations,
    }
