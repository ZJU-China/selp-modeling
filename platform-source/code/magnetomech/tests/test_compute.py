"""Tests for the CG modulus reader and the end-to-end computation."""
import json
import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from magnetomech import compute, field, modulus, physics as ph  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CG_SUMMARY = os.path.join(
    REPO, "CG", "CG_platform_handoff_20260907", "artifacts",
    "periodic_modulus_32chain", "rubber_elasticity", "rubber_elasticity_summary.json")


class TestModulusReader:
    def test_summary_present(self):
        assert os.path.isfile(CG_SUMMARY), "CG handoff summary missing"

    def test_read_affine(self):
        m = modulus.load_cg_modulus(CG_SUMMARY, "affine")
        assert m["kpa"] > 0 and 20 < m["kpa"] < 45
        approx_e = m["pa"] / 1000.0
        assert abs(approx_e - m["kpa"]) < 1e-6
        assert m["phantomKpa"] and m["phantomKpa"] < m["kpa"]

    def test_phantom_lower_than_affine(self):
        ph = modulus.load_cg_modulus(CG_SUMMARY, "phantom")
        af = modulus.load_cg_modulus(CG_SUMMARY, "affine")
        assert ph["kpa"] < af["kpa"]

    def test_explicit(self):
        m = modulus.resolve_explicit_or_cg({"modulusKpa": 25.0})
        assert m["source"] == "explicit" and m["pa"] == 25000.0

    def test_missing_file_raises(self):
        try:
            modulus.load_cg_modulus("/nonexistent/x.json", "affine")
            raised = False
        except FileNotFoundError:
            raised = True
        assert raised


class TestCompute:
    def make_params(self, phi=0.05, max_t=0.6, mode="uniform"):
        return {
            "modulusMode": "affine",
            "particle": {"phi": phi, "diameterNm": 10.0, "saturationAperM": 4.8e5},
            "field": {"mode": mode, "maxT": max_t, "heightMm": 10.0, "nPoints": 51},
            "temperatureK": 310.0, "coupling": 0.25,
        }

    def test_run_shape(self):
        result = compute.run(self.make_params())
        assert result["modulus"]["mode"] == "affine"
        assert result["modulus"]["pa"] and result["modulus"]["pa"] > 0
        assert len(result["curves"]) == 161
        assert len(result["layers"]) == 51
        assert result["layers"][0]["z"] == 0.0
        assert result["layers"][-1]["z"] == 0.01
        assert result["summary"]["youngKpa"] > 0

    def test_zero_field_no_deformation(self):
        result = compute.run(self.make_params(max_t=0.0))
        assert result["summary"]["maxContractionPct"] == 0.0
        for c in result["curves"]:
            assert c["mP"] == 0.0 and c["epsPar"] == 0.0

    def test_stronger_field_more_strain(self):
        low = compute.run(self.make_params(max_t=0.2))
        high = compute.run(self.make_params(max_t=1.0))
        assert high["summary"]["maxContractionPct"] > low["summary"]["maxContractionPct"]

    def test_more_filler_more_strain(self):
        small = compute.run(self.make_params(phi=0.02))
        big = compute.run(self.make_params(phi=0.2))
        assert big["summary"]["contractionPctAtMax"] > small["summary"]["contractionPctAtMax"]

    def test_incompressible_total(self):
        result = compute.run(self.make_params())
        for c in result["curves"][::20]:
            approx_v = c["epsPar"] + 2 * c["epsPerp"]
            assert abs(approx_v) < 1e-6

    def test_gradient_profile_layers_vary(self):
        params = self.make_params()
        params["field"] = {"mode": "gradient", "maxT": 0.6, "gradientDeltaT": 0.3,
                           "heightMm": 10.0, "nPoints": 21}
        result = compute.run(params)
        hs = [l["h"] for l in result["layers"]]
        assert hs[0] < hs[-1]
        assert result["layers"][-1]["h"] > result["layers"][0]["h"]

    def test_csv_profile(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixture_field.csv")
        with tempfile.TemporaryDirectory() as td:
            fp = os.path.join(td, "h.csv")
            with open(fp, "w") as f:
                f.write("x,y,z,H\n")
                for i in range(11):
                    f.write("0,0,%g,5000\n" % (i / 10.0))
            params = self.make_params()
            params["field"] = {"mode": "csv", "csvPath": fp, "heightMm": 10.0, "nPoints": 21}
            result = compute.run(params)
            for l in result["layers"]:
                assert 4000 <= l["h"] <= 6200


class TestWrite:
    def test_write_artifacts(self):
        import csv as _csv
        with tempfile.TemporaryDirectory() as td:
            result = compute.run({
                "modulusKpa": 31.0,
                "particle": {"phi": 0.05, "diameterNm": 10.0, "saturationAperM": 4.8e5},
                "field": {"mode": "uniform", "maxT": 0.6, "heightMm": 10.0, "nPoints": 21},
                "temperatureK": 310.0, "coupling": 0.25,
            })
            summary = compute.write_result(result, td)
            assert summary["youngKpa"] == 31.0
            for name in ("magnetomech.summary.json", "magnetomech.curve.csv", "magnetomech.layer.csv"):
                assert os.path.isfile(os.path.join(td, name))
            with open(os.path.join(td, "magnetomech.curve.csv")) as f:
                rows = list(_csv.reader(f))
            assert rows[0][0] == "h_AperM"
            assert len(rows) == 162
            with open(os.path.join(td, "magnetomech.summary.json")) as f:
                data = json.load(f)
            assert data["summary"]["youngKpa"] == 31.0


class TestRender:
    def make_params(self):
        return {
            "modulusKpa": 31.0,
            "particle": {"phi": 0.05, "diameterNm": 10.0, "saturationAperM": 4.8e5},
            "field": {"mode": "uniform", "maxT": 0.6, "heightMm": 10.0, "nPoints": 21},
            "temperatureK": 310.0, "coupling": 0.25,
        }

    def test_render_produces_png(self):
        from magnetomech import render as rnd
        result = compute.run(self.make_params())
        with tempfile.TemporaryDirectory() as td:
            filename = rnd.render_final_image(result, td)
            assert filename == "final_simulation.png"
            path = os.path.join(td, filename)
            assert os.path.isfile(path)
            with open(path, "rb") as f:
                assert f.read(8) == b"\x89PNG\r\n\x1a\n"


if __name__ == "__main__":
    import traceback
    failures = 0
    for cls in (TestModulusReader, TestCompute, TestWrite):
        inst = cls()
        for name in [n for n in dir(inst) if n.startswith("test_")]:
            try:
                getattr(inst, name)()
                print("  ok", name)
            except Exception:
                traceback.print_exc()
                failures += 1
                print("  FAIL", name)
    print(failures == 0 and "ALL PASS" or f"{failures} FAILURE(S)")
    sys.exit(1 if failures else 0)

class TestComposite:
    """The composite, built on an explicit modulus so the CG network
    is not needed."""

    def approx(self, a, b, tol=1e-6):
        assert abs(a - b) <= tol, "%r != %r" % (a, b)

    def _params(self, **extra):
        p = {
            "magnetomech": {"modulusMode": "explicit", "modulusKpa": 600.0},
            "particle": {"phi": 0.05, "diameterNm": 10.0, "saturationAperM": 4.8e5},
            "field": {"mode": "uniform", "maxT": 0.6, "heightMm": 10.0, "nPoints": 51},
            "temperatureK": 310.0, "coupling": 0.25,
        }
        p.update(extra)
        return p

    def test_absent_block_is_unchanged(self):
        r = compute.run(self._params())
        assert r["config"]["composite"] is None
        assert r["config"]["effectiveYoungSource"] == "cg-network"
        self.approx(r["config"]["effectiveYoungKpa"], 600.0)

    def test_water_recomputed_not_trusted(self):
        species = {"polymer": {"phi": 0.62}, "nanoparticle": {"phi": 0.05},
                   "water": {"phi": 0.99}}
        r = compute.run(self._params(composite={"species": species}))
        c = r["config"]["composite"]
        self.approx(c["phis"]["water"], 0.33)
        self.approx(c["phiTotal"], 1.0)

    def test_only_the_modelled_phases_are_reported(self):
        # A config naming a phase outside the model must not have it counted
        # into the remainder, which would quietly change the stiffness.
        r = compute.run(self._params(composite={"species": {
            "polymer": {"phi": 0.62}, "nanoparticle": {"phi": 0.05},
            "ion": {"phi": 0.10}}}))
        c = r["config"]["composite"]
        assert set(c["phis"]) == {"polymer", "nanoparticle", "water"}
        self.approx(c["phis"]["water"], 0.33)

    def test_only_nanoparticles_drive_the_magnetic_terms(self):
        species = {"polymer": {"phi": 0.62}, "nanoparticle": {"phi": 0.08}}
        r = compute.run(self._params(composite={"species": species}))
        self.approx(r["config"]["volFracPhi"], 0.08)
        assert r["config"]["effectiveYoungSource"] == "composite"

    def test_dilution_softens_the_sample(self):
        species = {"polymer": {"phi": 0.5}, "nanoparticle": {"phi": 0.05}}
        bare = compute.run(self._params())
        loaded = compute.run(self._params(composite={"species": species}))
        assert loaded["config"]["effectiveYoungKpa"] < bare["config"]["effectiveYoungKpa"]


def _run_field(field_cfg):
    return compute.run({
        "magnetomech": {"modulusMode": "explicit", "modulusKpa": 600.0},
        "particle": {"phi": 0.05, "saturationAperM": 4.3e5, "diameterNm": 10.0},
        "field": field_cfg, "temperatureK": 310.0, "coupling": 0.25,
        "demagFactor": 1.0 / 3.0,
    })


def _csv_profile(body):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as f:
        f.write(body)
    try:
        return field.make_profile("csv", {"heightMm": 10.0, "nPoints": 51,
                                          "csvPath": path})
    finally:
        os.unlink(path)


class TestAppliedFieldRange:
    """The sweep and the reported field must cover the peak in the sample.

    The profile is ordered by position, so its first point is the weakest one in
    a gradient or a rising csv. Sweeping only that far under-reports every
    headline number, and reporting the config's maxT instead of the file's own
    peak misreports it again.
    """

    def test_gradient_sweep_reaches_the_peak(self):
        # gradient_profile rises with z, so profile[0] is the weakest point.
        r = _run_field({"mode": "gradient", "maxT": 0.6, "gradientDeltaT": 0.2,
                        "heightMm": 10.0, "nPoints": 51})
        assert r["summary"]["appliedBT"] == pytest.approx(0.8, abs=1e-6)
        assert r["curves"][-1]["t"] == pytest.approx(0.8, abs=1e-6)

    def test_uniform_sweep_matches_maxT(self):
        r = _run_field({"mode": "uniform", "maxT": 0.6, "heightMm": 10.0,
                        "nPoints": 51})
        assert r["summary"]["appliedBT"] == pytest.approx(0.6, abs=1e-6)
        assert r["curves"][-1]["t"] == pytest.approx(0.6, abs=1e-6)

    def test_csv_reports_the_field_in_the_file_not_the_config_default(self):
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write("z,B\n0,0.1\n0.005,0.35\n0.01,0.9\n")
        try:
            # maxT stays at the 0.6 default, but the file peaks at 0.9.
            r = _run_field({"mode": "csv", "csvPath": path, "maxT": 0.6,
                            "heightMm": 10.0, "nPoints": 51})
            assert r["summary"]["appliedBT"] == pytest.approx(0.9, abs=1e-4)
            assert r["curves"][-1]["t"] == pytest.approx(0.9, abs=1e-4)
        finally:
            os.unlink(path)


class TestFieldCsvUnits:
    """A position column's unit decides whether the profile is usable at all."""

    def _b(self, body):
        return [ph.MU0 * h for _, h in _csv_profile(body)]

    def test_mm_suffix_is_honoured(self):
        b = self._b("z_mm,B\n0,0.1\n5,0.35\n10,0.9\n")
        assert min(b) == pytest.approx(0.1, abs=1e-3)
        assert max(b) == pytest.approx(0.9, abs=1e-3)

    def test_metre_column_is_honoured(self):
        b = self._b("z,B\n0,0.1\n0.005,0.35\n0.01,0.9\n")
        assert min(b) == pytest.approx(0.1, abs=1e-3)
        assert max(b) == pytest.approx(0.9, abs=1e-3)

    def test_bare_z_in_mm_is_rejected_not_silently_clamped(self):
        # Read as metres this spans 0..10 m, so only the origin row would count
        # and the whole sample would see a flat field.
        with pytest.raises(ValueError) as exc:
            _csv_profile("z,B\n0,0.1\n5,0.35\n10,0.9\n")
        assert "z_mm" in str(exc.value)

    def test_profile_that_stops_short_is_rejected(self):
        with pytest.raises(ValueError):
            _csv_profile("z,B\n0,0.1\n0.002,0.2\n")
