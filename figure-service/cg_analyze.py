import glob, os, subprocess, sys
import numpy as np
import MDAnalysis as mda
from MDAnalysis.analysis import rms

workdir, taskdir = sys.argv[1], sys.argv[2]
tprs = sorted(glob.glob(os.path.join(workdir, "*.tpr")))
tops = sorted(glob.glob(os.path.join(workdir, "*.gro"))) or sorted(glob.glob(os.path.join(workdir, "*.pdb")))
if not tprs or not tops:
    sys.exit("need tpr and gro/pdb in " + workdir)
tpr, top = tprs[0], tops[0]
raw = [x for x in glob.glob(os.path.join(workdir, "*.xtc")) if "merged_for_analysis" not in x]
# md.part000N.xtc is often a hard link to md.xtc; merging both duplicates every frame.
seen, xtcs = set(), []
for x in sorted(raw, key=lambda v: (0 if v.endswith("/md.xtc") else 1, v)):
    st = os.stat(x)
    key = (st.st_dev, st.st_ino)
    if key in seen:
        continue
    seen.add(key)
    xtcs.append(x)
merged = os.path.join(workdir, "merged_for_analysis.xtc")
if len(xtcs) > 1:
    subprocess.run(["gmx", "trjcat", "-f"] + xtcs + ["-o", merged, "-cat"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
else:
    merged = xtcs[0]

from MDAnalysis.coordinates.XTC import XTCReader
n_atoms = XTCReader(merged).n_atoms
lines = open(top).read().splitlines()
natoms = int(lines[1].strip())
body = lines[2:2 + natoms]
sliced = os.path.join(workdir, "protein_top_for_analysis.gro")
with open(sliced, "w") as fh:
    fh.write("protein\n%d\n" % n_atoms)
    fh.write("\n".join(body[:n_atoms]))
    fh.write("\n" + lines[-1] + "\n")
u = mda.Universe(sliced, merged)
ref = u.atoms.positions.copy()
rows = []
for ts in u.trajectory:
    pos = u.atoms.positions
    center = pos.mean(axis=0)
    rg = float(np.sqrt(((pos - center) ** 2).sum(axis=1).mean()))
    e2e = float(np.linalg.norm(pos[-1] - pos[0]))
    # Minimum-image correction before RMSD: wrapped molecules jump by a box length
    # and otherwise produce RMSD values of tens of nm.
    d = pos - ref
    box = getattr(u, "dimensions", None)
    if box is not None:
        box = np.asarray(box[:3], dtype=float)
        if np.all(box > 0):
            d = d - box * np.round(d / box)
    corrected = ref + d
    rmsd = float(rms.rmsd(corrected, ref, superposition=True))
    rows.append((float(ts.time), rg, e2e, rmsd))

analysis = os.path.join(taskdir, "cache", "analysis")
os.makedirs(analysis, exist_ok=True)
def write(name, idx, header):
    with open(os.path.join(analysis, name), "w") as fh:
        fh.write(header)
        for i, row in enumerate(rows):
            fh.write("0\t%d\t%.6f\n" % (i, row[idx]))
write("rg.dat", 1, "# replica step rg(nm)\n")
write("e2e.dat", 2, "# replica step e2e(nm)\n")
write("rmsd.dat", 3, "# replica step rmsd(nm)\n")

data_dir = os.path.join(workdir, "analysis")
os.makedirs(data_dir, exist_ok=True)
with open(os.path.join(data_dir, "thermo.csv"), "w") as fh:
    fh.write("time_ps,rg_nm,e2e_nm,rmsd_nm\n")
    for t, rg, e2e, rmsd in rows:
        fh.write("%.3f,%.5f,%.5f,%.5f\n" % (t, rg, e2e, rmsd))
print("frames", len(rows), "top", os.path.basename(top))
