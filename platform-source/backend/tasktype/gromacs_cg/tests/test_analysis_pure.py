"""Pure unit tests for the GROMACS CG analysis package (no MDAnalysis needed).

Run with: python3 -m unittest discover -s tests -p 'test_analysis_pure.py'
(or any interpreter with numpy on sys.path).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

_GC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _GC_DIR)

from lib.analysis import paths, writers  # noqa: E402
from lib.analysis.network import parse_network, crosslink_distances  # noqa: E402
from lib.analysis.structure import (  # noqa: E402
    _rgyr, _e2e, _chain_rg_stats, resolve_chain_layout, frame_steps,
)
import numpy as np  # noqa: E402


class TestPaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cg_paths_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_task_config_defaults(self):
        cfg = paths.load_task_config(self.tmp)
        self.assertEqual(cfg["stepsPerCycle"], 500000)
        self.assertEqual(cfg["timestepFs"], 20)
        self.assertEqual(cfg["numReplicas"], 1)

    def test_load_task_config_reads_defaults(self):
        d = os.path.join(self.tmp, "scripts")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "task_config.json"), "w") as f:
            json.dump({"defaults": {"stepsPerCycle": 123, "timestepFs": 10}}, f)
        cfg = paths.load_task_config(self.tmp)
        self.assertEqual(cfg["stepsPerCycle"], 123)
        self.assertEqual(cfg["timestepFs"], 10)

    def test_discover_dcds_sorted(self):
        traj = os.path.join(self.tmp, "cache", "trajectory")
        os.makedirs(traj, exist_ok=True)
        for name in ("replica_10.dcd", "replica_2.dcd", "topology.pdb"):
            with open(os.path.join(traj, name), "w") as f:
                f.write("x")
        dcds = paths.discover_dcds(traj)
        self.assertEqual([os.path.basename(p) for p in dcds], ["replica_2.dcd", "replica_10.dcd"])

    def test_find_task_file(self):
        sub = os.path.join(self.tmp, "input")
        os.makedirs(sub, exist_ok=True)
        with open(os.path.join(sub, "network.json"), "w") as f:
            f.write("{}")
        net = paths.network_json_path(self.tmp)
        self.assertIsNotNone(net)
        self.assertTrue(str(net).endswith("network.json"))
        with open(os.path.join(self.tmp, "crosslink_pairs.tsv"), "w") as f:
            f.write("a")
        tsv = paths.crosslink_tsv_path(self.tmp)
        self.assertIsNotNone(tsv)
        self.assertTrue(str(tsv).endswith("crosslink_pairs.tsv"))


class TestWriters(unittest.TestCase):
    def test_write_dat_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "rg.dat")
            writers.write_dat(p, "replica step rg(A)", [(0, 100, 12.5), (0, 200, "")])
            self.assertEqual(writers.count_rows(p), 2)
            with open(p) as f:
                lines = f.read().splitlines()
            self.assertTrue(lines[0].startswith("# replica step rg(A)"))
            self.assertEqual(lines[1], "0\t100\t12.5")


class TestStructurePure(unittest.TestCase):
    def test_rgyr(self):
        pos = np.zeros((3, 3))
        pos[0] = [1, 0, 0]
        pos[1] = [-1, 0, 0]
        pos[2] = [0, 0, 0]
        self.assertAlmostEqual(_rgyr(pos), np.sqrt(2 / 3), places=6)

    def test_e2e(self):
        pos = np.zeros((3, 3))
        pos[0] = [1, 0, 0]
        pos[2] = [0, 2, 0]
        self.assertAlmostEqual(_e2e(pos), np.sqrt(5), places=6)

    def test_chain_layout(self):
        net = {"n_chains": 2, "beads_per_chain": 3}
        self.assertEqual(resolve_chain_layout(6, net), (2, 3))
        self.assertEqual(resolve_chain_layout(7, net), (1, 7))
        self.assertEqual(resolve_chain_layout(4, None), (1, 4))

    def test_chain_rg_stats(self):
        # 2 chains x 2 beads: chain0 = [2,0,0],[0,0,0] -> rg 1;
        # chain1 = [0,0,0],[0,0,0] -> rg 0 => (mean, min, max) = (0.5, 0, 1).
        pos = np.zeros((4, 3))
        pos[0] = [2, 0, 0]
        mean, lo, hi = _chain_rg_stats(pos, 2, 2)
        self.assertAlmostEqual(mean, 0.5, places=6)
        self.assertAlmostEqual(lo, 0.0, places=6)
        self.assertAlmostEqual(hi, 1.0, places=6)

    def test_frame_steps_fallback(self):
        steps = frame_steps("/nonexistent", "s1", 5, 20, 1000)
        self.assertEqual(steps, [0, 1000, 2000, 3000, 4000])
        self.assertEqual(frame_steps("/nonexistent", "s1", 0, 20, 1000), [])


class TestNetworkPure(unittest.TestCase):
    def _net(self):
        return {
            "schema_version": 1,
            "n_chains": 2,
            "beads_per_chain": 3,
            "seed": 1,
            "edges": [
                {"chain_a": 1, "chain_b": 2, "site_a": 2, "site_b": 3,
                 "atom_a": 0, "atom_b": 0, "periodic_shift": [0, 0, 0]},
            ],
        }

    def test_parse_network(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(self._net(), f)
            p = f.name
        try:
            net = parse_network(p)
        finally:
            os.unlink(p)
        self.assertEqual(net["n_chains"], 2)
        self.assertEqual(net["beads_per_chain"], 3)
        # chain 1 site 2 -> index 1; chain 2 site 3 -> index 2*3 + 2 = 8? no:
        # (2-1)*3 + (3-1) = 3 + 2 = 5
        self.assertEqual(net["links"], [(1, 5)])

    def test_crosslink_distances(self):
        pos = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 0],
                        [0, 0, 0], [0, 0, 0], [4, 0, 0]], dtype=float)
        dists = crosslink_distances(pos, [(1, 5)])
        self.assertAlmostEqual(float(dists[0]), 3.0, places=6)


if __name__ == "__main__":
    unittest.main()