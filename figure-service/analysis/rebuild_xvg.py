#!/usr/bin/env python3
"""Rebuild the GROMACS analysis XVG files that back the CG/mechanics figures.

The original distances.xvg / thermo.xvg were produced ad hoc with
`gmx distance` and `gmx energy`; no generator script was kept. This script
reproduces them from the run's md.tpr / md.xtc / md.edr:

  * the crosslink selection is read from the existing distances.xvg header
    (or supplied with --pairs as "i j" lines),
  * the energy terms are read from the existing thermo.xvg legends (or supplied
    with --terms), then `gmx energy` is fed those names on stdin.

Usage:
  rebuild_xvg.py --dir <run dir> --out <out dir> [--pairs pairs.txt]
                 [--terms "Temperature,Pressure,Volume"] [--skip-distance]
                 [--skip-energy]
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

GMX = os.environ.get("GMX") or ("/opt/gromacs/bin/gmx" if os.path.exists("/opt/gromacs/bin/gmx") else "gmx")


def pick(dirpath, ext):
    direct = dirpath / ("md." + ext)
    if direct.exists():
        return direct
    hits = sorted(dirpath.glob("*." + ext))
    return hits[0] if hits else None


def read_selection(xvg):
    if not xvg or not xvg.exists():
        return None
    text = xvg.read_text(errors="ignore")
    m = re.search(r"-select '([^']+)'", text) or re.search(r'-select "([^"]+)"', text)
    return m.group(1) if m else None


def read_terms(xvg):
    if not xvg or not xvg.exists():
        return []
    terms = []
    for line in xvg.read_text(errors="ignore").splitlines():
        m = re.search(r'@ s\d+ legend "([^"]+)"', line)
        if m:
            terms.append(m.group(1))
    return terms


def run(cmd, cwd, stdin_text=None):
    return subprocess.run(cmd, cwd=str(cwd), input=stdin_text, text=True,
                          capture_output=True, timeout=3600)


def data_rows(xvg):
    if not xvg.exists():
        return 0
    n = 0
    for line in xvg.read_text(errors="ignore").splitlines():
        s = line.strip()
        if s and s[0] not in "#@":
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pairs", default=None)
    ap.add_argument("--terms", default=None)
    ap.add_argument("--skip-distance", action="store_true")
    ap.add_argument("--skip-energy", action="store_true")
    args = ap.parse_args()

    rundir = Path(args.dir).resolve()
    outdir = Path(args.out).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    manifest = {"runDir": str(rundir), "gmx": GMX, "commands": []}

    if not args.skip_distance:
        # GROMACS 2025.4 cannot read the 2026.1 tpr (version 138 vs 137).
        # md.gro carries the same atom numbering and is accepted by gmx distance.
        tpr, xtc = (pick(rundir, "gro") or pick(rundir, "tpr")), pick(rundir, "xtc")
        selection = None
        if args.pairs:
            pairs = []
            for line in Path(args.pairs).read_text().splitlines():
                parts = [p for p in re.split(r"[\s,]+", line.strip()) if p]
                if len(parts) >= 2:
                    pairs.append("atomnr %s plus atomnr %s" % (parts[0], parts[1]))
            selection = "; ".join(pairs)
        if not selection:
            selection = read_selection(rundir / "distances.xvg")
        if tpr and xtc and selection:
            out = outdir / "distances.xvg"
            cmd = [GMX, "distance", "-s", str(tpr), "-f", str(xtc), "-select", selection, "-oall", str(out)]
            res = run(cmd, rundir)
            (outdir / "distance.out").write_text(res.stdout + res.stderr)
            manifest["commands"].append({"cmd": cmd, "rc": res.returncode})
            manifest["distance"] = {"rows": data_rows(out), "pairs": selection.count("plus")}
        else:
            manifest["distance"] = {"error": "missing tpr/xtc/selection"}

    if not args.skip_energy:
        edr = pick(rundir, "edr")
        terms = [t.strip() for t in args.terms.split(",")] if args.terms else read_terms(rundir / "thermo.xvg")
        if edr and terms:
            out = outdir / "thermo.xvg"
            cmd = [GMX, "energy", "-f", str(edr), "-o", str(out)]
            res = run(cmd, rundir, "\n".join(terms) + "\n")
            (outdir / "energy.out").write_text(res.stdout + res.stderr)
            manifest["commands"].append({"cmd": cmd, "terms": terms, "rc": res.returncode})
            manifest["energy"] = {"rows": data_rows(out), "terms": terms}
        else:
            manifest["energy"] = {"error": "missing edr/terms"}

    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
