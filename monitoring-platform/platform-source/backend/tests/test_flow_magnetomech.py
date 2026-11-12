"""Tests for flow_magnetomech's synthesize step.

These cover the input preparation the Parameters panel drives: recomputing water
as the remainder, refusing an unusable fraction set, and rejecting a field
profile whose header the consumer could not read.
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
# .../backend/tests -> .../backend/tasktype, where the tasktype packages live.
TASKTYPE_DIR = os.path.join(os.path.dirname(HERE), "tasktype")
REPO = os.path.dirname(os.path.dirname(TASKTYPE_DIR))
sys.path.insert(0, TASKTYPE_DIR)

from flow_magnetomech.main import check_field_csv, resolve_composite, synthesize  # noqa: E402


def config(**over):
    cfg = {
        "composite": {"species": {
            "polymer": {"phi": 0.62},
            "nanoparticle": {"phi": 0.05},
        }},
        "field": {"mode": "uniform", "maxT": 0.6, "heightMm": 10.0, "nPoints": 11},
        "particle": {"phi": 0.05, "saturationAperM": 4.3e5},
        "magnetomech": {"modulusMode": "affine"},
        "temperatureK": 310.0,
        "coupling": 0.25,
        "demagFactor": 1.0 / 3.0,
    }
    for key, value in over.items():
        cfg[key] = value
    return cfg


class ResolveComposite(unittest.TestCase):
    def test_water_is_the_remainder(self):
        phis = resolve_composite(config())
        self.assertAlmostEqual(phis["polymer"], 0.62)
        self.assertAlmostEqual(phis["nanoparticle"], 0.05)
        self.assertAlmostEqual(phis["water"], 0.33)
        self.assertAlmostEqual(sum(phis.values()), 1.0, places=12)

    def test_a_stored_water_value_is_ignored(self):
        """Water is computed, so a hand-edited value cannot desync the total."""
        cfg = config()
        cfg["composite"]["species"]["water"] = {"phi": 0.99}
        self.assertAlmostEqual(resolve_composite(cfg)["water"], 0.33)

    def test_flat_species_shape_is_accepted(self):
        cfg = config(composite={"polymer": 0.7, "nanoparticle": 0.3})
        phis = resolve_composite(cfg)
        self.assertAlmostEqual(phis["polymer"], 0.7)
        self.assertAlmostEqual(phis["water"], 0.0)

    def test_missing_composite_is_all_zero_not_an_error(self):
        phis = resolve_composite({})
        self.assertEqual(phis["polymer"], 0.0)
        self.assertAlmostEqual(phis["water"], 1.0)


class FieldCsv(unittest.TestCase):
    def test_accepts_position_and_field_columns(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("z,B\n0,0.0\n10,0.6\n")
            path = f.name
        try:
            ok, note = check_field_csv(path)
            self.assertTrue(ok, note)
            self.assertIn("'z'", note)
        finally:
            os.unlink(path)

    def test_case_insensitive_like_field_py(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("X,H\n0,0.0\n")
            path = f.name
        try:
            self.assertTrue(check_field_csv(path)[0])
        finally:
            os.unlink(path)

    def test_rejects_missing_position_column_and_lists_what_it_found(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("depth,value\n0,1\n")
            path = f.name
        try:
            ok, msg = check_field_csv(path)
            self.assertFalse(ok)
            self.assertIn("position column", msg)
            self.assertIn("depth", msg)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        ok, msg = check_field_csv("/nonexistent/profile.csv")
        self.assertFalse(ok)
        self.assertIn("not found", msg)


class Synthesize(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _params(self):
        with open(os.path.join(self.tmp, "input", "params.json")) as f:
            return json.load(f)

    def test_writes_profile_and_params(self):
        res = synthesize(self.tmp, config())
        self.assertTrue(res["ok"], res)
        self.assertAlmostEqual(res["phis"]["water"], 0.33)
        self.assertAlmostEqual(res["phiTotal"], 1.0, places=12)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "input", "field_profile.csv")))
        params = self._params()
        self.assertAlmostEqual(params["composite"]["phis"]["water"], 0.33)
        self.assertAlmostEqual(params["temperatureK"], 310.0)

    def test_uniform_profile_is_flat_and_sized_by_npoints(self):
        res = synthesize(self.tmp, config())
        with open(os.path.join(self.tmp, res["profile"])) as f:
            rows = f.read().strip().splitlines()
        # header + nPoints rows
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0], "z_mm,B_T")
        self.assertAlmostEqual(float(rows[1].split(",")[1]), 0.6)
        self.assertAlmostEqual(float(rows[-1].split(",")[1]), 0.6)

    def test_gradient_profile_rises_across_the_height_like_field_py(self):
        # field.gradient_profile is maxT at z=0 rising by deltaT. The record has
        # to agree: written the other way it misstates the field that was applied.
        cfg = config()
        cfg["field"].update({"mode": "gradient", "maxT": 0.6, "gradientDeltaT": 0.2})
        res = synthesize(self.tmp, cfg)
        with open(os.path.join(self.tmp, res["profile"])) as f:
            rows = [r for r in f.read().strip().splitlines()[1:] if r and not r.startswith("#")]
        self.assertAlmostEqual(float(rows[0].split(",")[1]), 0.6)
        self.assertAlmostEqual(float(rows[-1].split(",")[1]), 0.8, places=6)

    def test_recorded_gradient_matches_what_the_compute_generates(self):
        import importlib.util
        sys.path.insert(0, os.path.join(REPO, "code"))
        from magnetomech import field as fld, physics as ph
        cfg = config()
        cfg["field"].update({"mode": "gradient", "maxT": 0.6, "gradientDeltaT": 0.2,
                             "heightMm": 10.0, "nPoints": 9})
        res = synthesize(self.tmp, cfg)
        with open(os.path.join(self.tmp, res["profile"])) as f:
            rows = [r for r in f.read().strip().splitlines()[1:] if r and not r.startswith("#")]
        recorded = [float(r.split(",")[1]) for r in rows]
        actual = [ph.MU0 * h for _, h in fld.gradient_profile(
            0.010, 9, max_t=0.6, delta_t=0.2)]
        for got, want in zip(recorded, actual):
            self.assertAlmostEqual(got, want, places=5)

    def test_fractions_leaving_no_water_are_fine(self):
        cfg = config()
        cfg["composite"]["species"] = {
            "polymer": {"phi": 0.95}, "nanoparticle": {"phi": 0.05}}
        res = synthesize(self.tmp, cfg)
        self.assertTrue(res["ok"], res)
        self.assertAlmostEqual(res["phis"]["water"], 0.0)

    def test_overfull_fractions_are_refused_before_writing(self):
        cfg = config()
        cfg["composite"]["species"]["polymer"] = {"phi": 0.95}
        cfg["composite"]["species"]["nanoparticle"] = {"phi": 0.9}
        res = synthesize(self.tmp, cfg)
        self.assertFalse(res["ok"])
        self.assertEqual(res["stage"], "composite")
        self.assertIn("must not exceed 1", res["error"])
        # Nothing was written, so a rejected set cannot half-apply.
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "input", "params.json")))

    def test_csv_mode_without_a_file_is_refused(self):
        cfg = config()
        cfg["field"]["mode"] = "csv"
        res = synthesize(self.tmp, cfg)
        self.assertFalse(res["ok"])
        self.assertEqual(res["stage"], "field")
        self.assertIn("no field file", res["error"])

    def test_csv_mode_with_a_bad_header_is_refused(self):
        os.makedirs(os.path.join(self.tmp, "input"), exist_ok=True)
        with open(os.path.join(self.tmp, "input", "bad.csv"), "w") as f:
            f.write("depth,value\n0,1\n")
        cfg = config()
        cfg["field"].update({"mode": "csv", "csvPath": "bad.csv"})
        res = synthesize(self.tmp, cfg)
        self.assertFalse(res["ok"])
        self.assertEqual(res["stage"], "field")
        self.assertIn("position column", res["error"])

    def test_csv_mode_with_a_good_header_is_accepted(self):
        os.makedirs(os.path.join(self.tmp, "input"), exist_ok=True)
        with open(os.path.join(self.tmp, "input", "good.csv"), "w") as f:
            f.write("z_mm,B\n0,0.0\n5,0.3\n10,0.6\n")
        cfg = config()
        cfg["field"].update({"mode": "csv", "csvPath": "input/good.csv"})
        res = synthesize(self.tmp, cfg)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["fieldMode"], "csv")
        self.assertEqual(res["fieldFile"], "input/good.csv")
        self.assertIn("z_mm", res["fieldNote"])
        # The record names the uploaded file so the applied profile is traceable.
        with open(os.path.join(self.tmp, res["profile"])) as f:
            self.assertIn("input/good.csv", f.read())

    def test_csv_mode_resolves_a_bare_filename_against_input(self):
        os.makedirs(os.path.join(self.tmp, "input"), exist_ok=True)
        with open(os.path.join(self.tmp, "input", "bare.csv"), "w") as f:
            f.write("z_mm,B\n0,0.0\n10,0.6\n")
        cfg = config()
        cfg["field"].update({"mode": "csv", "csvPath": "bare.csv"})
        res = synthesize(self.tmp, cfg)
        self.assertTrue(res["ok"], res)

    def test_csv_in_mm_under_a_bare_z_column_is_refused(self):
        os.makedirs(os.path.join(self.tmp, "input"), exist_ok=True)
        with open(os.path.join(self.tmp, "input", "mm.csv"), "w") as f:
            f.write("z,B\n0,0.1\n5,0.35\n10,0.9\n")
        cfg = config()
        cfg["field"].update({"mode": "csv", "csvPath": "mm.csv"})
        res = synthesize(self.tmp, cfg)
        self.assertFalse(res["ok"])
        self.assertIn("z_mm", res["error"])

    def test_csv_from_another_origin_is_refused_with_that_reason(self):
        os.makedirs(os.path.join(self.tmp, "input"), exist_ok=True)
        with open(os.path.join(self.tmp, "input", "offset.csv"), "w") as f:
            f.write("z_mm,B\n100.5,0.1\n150.5,0.9\n")
        cfg = config()
        cfg["field"].update({"mode": "csv", "csvPath": "offset.csv"})
        res = synthesize(self.tmp, cfg)
        self.assertFalse(res["ok"])
        self.assertIn("another origin", res["error"])

    def test_csv_in_mm_with_an_mm_column_is_accepted(self):
        os.makedirs(os.path.join(self.tmp, "input"), exist_ok=True)
        with open(os.path.join(self.tmp, "input", "mm.csv"), "w") as f:
            f.write("z_mm,B\n0,0.1\n5,0.35\n10,0.9\n")
        cfg = config()
        cfg["field"].update({"mode": "csv", "csvPath": "mm.csv"})
        res = synthesize(self.tmp, cfg)
        self.assertTrue(res["ok"], res)
        self.assertIn("(mm)", res["fieldNote"])

    def test_csv_mode_with_a_missing_file_is_refused(self):
        cfg = config()
        cfg["field"].update({"mode": "csv", "csvPath": "gone.csv"})
        res = synthesize(self.tmp, cfg)
        self.assertFalse(res["ok"])
        self.assertIn("was not found", res["error"])


if __name__ == "__main__":
    unittest.main()
