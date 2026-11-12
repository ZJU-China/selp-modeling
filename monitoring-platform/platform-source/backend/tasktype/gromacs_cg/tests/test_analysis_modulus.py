"""Pure unit tests for the GROMACS CG modulus analysis module.

No MDAnalysis/numpy required — network32.rubber is pure stdlib. Needs a real
network.json on disk (network topology only); the artifacts live outside git, so
the test builds a small synthetic 2-chain periodic network instead.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

_GC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _GC_DIR)

from lib.analysis import modulus, paths  # noqa: E402


def make_task_dir(tmp, volume_nm3=8.0, temperature_k=None):
    """A minimal task dir: input/network.json + cache/analysis/box.dat."""
    inp = os.path.join(tmp, "input")
    analysis = os.path.join(tmp, "cache", "analysis")
    os.makedirs(inp, exist_ok=True)
    os.makedirs(analysis, exist_ok=True)
    network = {
        "schema_version": 1,
        "n_chains": 2,
        "beads_per_chain": 100,
        "seed": 7,
        "edges": [
            {"chain_a": 1, "chain_b": 2, "site_a": 50, "site_b": 50,
             "periodic_shift": [0, 0, 0]},
            {"chain_a": 1, "chain_b": 2, "site_a": 80, "site_b": 80,
             "periodic_shift": [0, 0, 0]},
        ],
    }
    with open(os.path.join(inp, "network.json"), "w") as f:
        json.dump(network, f)
    side = volume_nm3 ** (1.0 / 3.0)
    with open(os.path.join(analysis, "box.dat"), "w") as f:
        f.write("# replica step box_x(nm) box_y(nm) box_z(nm)\n")
        f.write("0\t0\t%.6f\t%.6f\t%.6f\n" % (side, side, side))
        f.write("0\t0\t%.6f\t%.6f\t%.6f\n" % (side, side, side))
    if temperature_k:
        scripts = os.path.join(tmp, "scripts")
        os.makedirs(scripts, exist_ok=True)
        with open(os.path.join(scripts, "task_config.json"), "w") as f:
            json.dump({"modulus": {"temperatureK": temperature_k}}, f)
    return tmp


class TestModulusAnalysis(unittest.TestCase):
    def test_no_network_ok_false(self):
        with tempfile.TemporaryDirectory() as d:
            r = modulus.analyze(d, paths.load_task_config(d))
            self.assertFalse(r.get("ok"))
            self.assertIn("network.json", r.get("error", ""))

    def test_no_box_falls_back_to_none(self):
        with tempfile.TemporaryDirectory() as d:
            inp = os.path.join(d, "input")
            os.makedirs(inp)
            with open(os.path.join(inp, "network.json"), "w") as f:
                json.dump({"n_chains": 2, "seed": 0, "edges": []}, f)
            r = modulus.analyze(d, paths.load_task_config(d))
            self.assertFalse(r.get("ok"))
            self.assertIn("volume", r.get("error", ""))

    def test_analyze_writes_summary(self):
        with tempfile.TemporaryDirectory() as d:
            make_task_dir(d, volume_nm3=8.0)
            r = modulus.analyze(d, paths.load_task_config(d))
            self.assertTrue(r.get("ok"), r.get("error"))
            self.assertEqual(r["volume_source"], "box.dat")
            self.assertEqual(r["temperature_k_source"], "default")
            for rel in ("cache/analysis/rubber_elasticity_summary.json",
                        "output/rubber_elasticity_summary.json"):
                p = os.path.join(d, rel)
                self.assertTrue(os.path.isfile(p), rel)
                with open(p) as f:
                    s = json.load(f)
                self.assertIn("ensemble", s)
                self.assertIn("networks", s)
                self.assertIn("assumptions", s)
                self.assertEqual(s["ensemble"]["network_count"], 1)
                self.assertGreater(s["ensemble"]["young_incompressible_affine_kpa"], 0)
                self.assertAlmostEqual(
                    s["ensemble"]["young_incompressible_affine_kpa"],
                    3.0 * s["ensemble"]["affine_kpa"])

    def test_configured_temperature_and_volume(self):
        with tempfile.TemporaryDirectory() as d:
            make_task_dir(d, volume_nm3=8.0, temperature_k=325.0)
            scripts = os.path.join(d, "scripts")
            os.makedirs(scripts, exist_ok=True)
            with open(os.path.join(scripts, "task_config.json"), "w") as f:
                json.dump({"modulus": {"temperatureK": 325.0, "volumeNm3": 8.0}}, f)
            r = modulus.analyze(d, paths.load_task_config(d))
            self.assertTrue(r.get("ok"), r.get("error"))
            self.assertEqual(r["temperature_k"], 325.0)
            self.assertEqual(r["volume_source"], "config")
            self.assertEqual(r["temperature_k_source"], "config")


if __name__ == "__main__":
    unittest.main()