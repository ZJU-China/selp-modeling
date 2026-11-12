"""Integration tests for structure/network modules (MDAnalysis required).

Builds a small synthetic task dir (topology + DCD + network.json) and runs the
real module pipelines. Run with an MDAnalysis-enabled interpreter:
  /path/to/mdaenv/bin/python -m unittest discover -s tests -p 'test_analysis_mda.py'
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

try:
    import MDAnalysis as mda
    from MDAnalysis.coordinates.DCD import DCDWriter
    HAS_MDA = True
except ImportError:
    HAS_MDA = False

_GC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _GC_DIR)

from lib.analysis import paths, writers  # noqa: E402
from lib.analysis.structure import analyze as structure_analyze  # noqa: E402
from lib.analysis.network import analyze as network_analyze  # noqa: E402

def _pdb6():
    """6-atom PDB text (2 chains x 3 beads) at frame-0 positions."""
    names = ("BB", "SC1", "SC2", "BB", "SC1", "SC2")
    resids = (1, 1, 1, 2, 2, 2)
    chains = ("A", "A", "A", "B", "B", "B")
    lines = []
    for i, (name, resid, chain) in enumerate(zip(names, resids, chains), start=1):
        x, y, z = i - 1, 0.0, 0.0
        lines.append(
            f"ATOM  {i:5d} {name:<4s} LYS {chain}{resid:4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00"
        )
    return "\n".join(lines) + "\n"


@unittest.skipUnless(HAS_MDA, "MDAnalysis not available")
class TestMdaIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cg_analysis_")
        self.task = os.path.join(self.tmp, "task")
        traj = os.path.join(self.task, "cache", "trajectory")
        os.makedirs(traj, exist_ok=True)
        for d in (os.path.join(self.task, "output"),
                  os.path.join(self.task, "input"),
                  os.path.join(self.task, "scripts")):
            os.makedirs(d, exist_ok=True)

        topo = os.path.join(traj, "topology.pdb")
        with open(topo, "w") as f:
            f.write(_pdb6())
        self.topo = topo

        dcd = os.path.join(traj, "replica_0.dcd")
        n_frames = 3
        atoms = mda.Universe(topo).atoms
        with DCDWriter(dcd, len(atoms)) as w:
            for i in range(n_frames):
                u2 = mda.Universe(topo)
                u2.atoms.positions = np_pos(i)
                w.write(u2.atoms)
        self.dcd = dcd
        self.n_frames = n_frames

        with open(os.path.join(self.task, "scripts", "task_config.json"), "w") as f:
            json.dump({"defaults": {"stepsPerCycle": 500000, "timestepFs": 20}}, f)

        net = {
            "schema_version": 1,
            "n_chains": 2,
            "beads_per_chain": 3,
            "seed": 1,
            "edges": [
                {"chain_a": 1, "chain_b": 2, "site_a": 2, "site_b": 3,
                 "atom_a": 0, "atom_b": 0, "periodic_shift": [0, 0, 0]},
            ],
        }
        with open(os.path.join(self.task, "input", "network.json"), "w") as f:
            json.dump(net, f)
        self.cfg = paths.load_task_config(self.task)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_structure(self):
        res = structure_analyze(self.task, self.cfg)
        self.assertTrue(res["ok"])
        self.assertEqual(res["replicas"], 1)
        for name in ("rg.dat", "e2e.dat", "rmsd.dat", "chain_rg.dat", "box.dat"):
            p = os.path.join(paths.analysis_dir(self.task), name)
            self.assertTrue(os.path.isfile(p), name)

        # 6 atoms on the x-axis, step axis falls back to frame * stepsPerCycle
        # (no relax.xtc present) -> rows for frames 1..2 only.
        with open(os.path.join(paths.analysis_dir(self.task), "rg.dat")) as f:
            rg = [l.split() for l in f.read().splitlines() if not l.startswith("#")]
        self.assertEqual(len(rg), 2)
        # row order is (rep, step, value); first row step should equal spc.
        self.assertEqual(int(rg[0][1]), 500000)

        with open(os.path.join(paths.analysis_dir(self.task), "e2e.dat")) as f:
            e2e = [l.split() for l in f.read().splitlines() if not l.startswith("#")]
        self.assertAlmostEqual(float(e2e[0][2]), 5.0, places=4)  # first<->last bead

    def test_network(self):
        res = network_analyze(self.task, self.cfg)
        self.assertTrue(res["ok"])
        self.assertEqual(res["links"], 1)
        p = os.path.join(paths.analysis_dir(self.task), "crosslink.dat")
        with open(p) as f:
            rows = [l.split() for l in f.read().splitlines() if not l.startswith("#")]
        self.assertEqual(len(rows), 2)
        # link chain1 site2 (global idx 1) <-> chain2 site3 (global idx 5)
        # idx1 at (i+1), idx5 at (i+5): distance exactly 4 for every frame.
        self.assertAlmostEqual(float(rows[0][2]), 4.0, places=4)

        tp = os.path.join(paths.analysis_dir(self.task), "crosslink_table.tsv")
        with open(tp) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        self.assertTrue(lines[0].startswith("#"))
        self.assertEqual(len(lines) - 1, 1)
        self.assertAlmostEqual(float(lines[1].split()[4]), 4.0, places=4)  # ref


def np_pos(i):
    import numpy as np
    return np.array([[0 + i, 0, 0], [1 + i, 0, 0], [2 + i, 0, 0],
                     [3 + i, 0, 0], [4 + i, 0, 0], [5 + i, 0, 0]], dtype=float)


class TestWritersRows(unittest.TestCase):
    def test_write_dat_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.dat")
            writers.write_dat(p, "a b c", [(1, 2, 3)])
            self.assertEqual(writers.count_rows(p), 1)


if __name__ == "__main__":
    unittest.main()