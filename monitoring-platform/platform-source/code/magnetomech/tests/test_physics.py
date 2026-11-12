"""Unit tests for code/magnetomech (pure python, no heavy deps)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from magnetomech import physics as ph  # noqa: E402


def approx(a, b, tol=1e-6):
    assert abs(a - b) <= tol, "%r != %r (tol %g)" % (a, b, tol)


class TestLangevin:
    def test_zero_field_zero(self):
        approx(ph.langevin(0.0), 0.0, 1e-6)

    def test_small_field_curie_law(self):
        approx(ph.langevin(0.01), 0.01 / 3.0, 1e-4)
        approx(ph.langevin(1e-8), 1e-8 / 3.0, 1e-9)

    def test_saturation(self):
        assert ph.langevin(100.0) > 0.98
        assert ph.langevin(1e6) > 0.99999

    def test_odd(self):
        approx(ph.langevin(-1.0), -ph.langevin(1.0), 1e-6)


class TestMagnetization:
    def test_particle_moment_scale(self):
        d = 10e-9
        m = ph.particle_moment(480000, d)
        approx(m, 480000 * (3.14159265358979 / 6) * d ** 3, 1e-9)

    def test_high_field_saturates(self):
        m = ph.magnetization(4.8e5, 10e-9, 1e8, 310)
        assert m > 4.7e5

    def test_zero_field_zero(self):
        approx(ph.magnetization(4.8e5, 10e-9, 0, 310), 0.0, 1e-3)

    def test_internal_field_lowers_applied(self):
        h_int = ph.internal_field(5e4, 0.05, 4.8e5, 10e-9, 310)
        assert h_int < 5e4 and h_int > 0

    def test_no_filler_no_change(self):
        h_int = ph.internal_field(5e4, 0.0, 4.8e5, 10e-9, 310)
        approx(h_int, 5e4)


class TestStressStrain:
    def test_stress_zero_at_zero_mag(self):
        approx(ph.magnetic_stress(0.0, 0.05, 0.25), 0.0)

    def test_stress_scales_phi_and_m2(self):
        s1 = ph.magnetic_stress(1e5, 0.1, 0.25)
        s2 = ph.magnetic_stress(2e5, 0.1, 0.25)
        approx(s2, 4 * s1, 1e-6)

    def test_axial_strain_compressive(self):
        eps = ph.axial_strain(1000.0, 31000.0)
        approx(eps, -1000.0 / 31000.0)

    def test_transverse_expands_via_poisson(self):
        eps_t = ph.transverse_strain(1000.0, 31000.0)
        approx(eps_t, 0.5 * 1000.0 / 31000.0)

    def test_shear_modulus_change_smaller_than_stress(self):
        dg = ph.shear_modulus_change(1e5, 0.05, 0.25)
        s = ph.magnetic_stress(1e5, 0.05, 0.25)
        approx(dg, 0.75 * s)

    def test_incompressible_volume(self):
        s = 2000.0
        e = 40000.0
        eps_p = ph.axial_strain(s, e)
        eps_t = ph.transverse_strain(s, e)
        approx(eps_p + 2 * eps_t, 0.0)


class TestCurve:
    def test_magnetization_curve_endpoints(self):
        curve = ph.magnetization_curve(4.8e5, 10e-9, 310, 5e5, n=5)
        assert len(curve) == 5
        assert curve[0][1] < 1e-3
        assert curve[-1][1] > 4.0e5


if __name__ == "__main__":
    import traceback
    failures = 0
    for cls in (TestLangevin, TestMagnetization, TestStressStrain, TestCurve):
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
    def test_water_is_the_remainder(self):
        approx(ph.water_fraction({"polymer": 0.62, "nanoparticle": 0.05}), 0.33, 1e-9)
        approx(ph.water_fraction({"polymer": 0.5, "nanoparticle": 0.05, "water": 0.9}), 0.45, 1e-9)

    def test_the_modelled_phases_are_polymer_nanoparticle_water(self):
        # Two independent fractions plus the remainder. resolve_composite builds
        # the dict from this tuple, so a config naming anything else is ignored
        # rather than counted into the water remainder.
        assert ph.PHASES == ("polymer", "nanoparticle", "water")

    def test_single_phase_reproduces_plain_modulus(self):
        # Backward compatibility: a config with only polymer must not change the
        # network modulus, otherwise every existing result would shift.
        r = ph.composite_shear_modulus({"polymer": 1.0}, {}, 200000.0)
        approx(r["shearPa"], 200000.0, 1e-9)

    def test_dilution_softens(self):
        # The regression that motivated this model: an inverse/Reuss sum over
        # only the load-bearing phases *raised* G as polymer was diluted.
        full = ph.composite_shear_modulus({"polymer": 1.0}, {}, 200000.0)
        diluted = ph.composite_shear_modulus(
            {"polymer": 0.62, "nanoparticle": 0.05}, {}, 200000.0)
        assert diluted["shearPa"] < full["shearPa"]
        approx(diluted["shearPa"], 0.62 * 200000.0, 1e-6)

    def test_nonpolymer_phases_are_neutral_by_default(self):
        # Bulk magnetite is ~77 GPa; folding that in at phi=0.05 would predict a
        # GPa-scale composite for a sub-MPa elastomer, so it must stay off.
        r = ph.composite_shear_modulus(
            {"polymer": 0.62, "nanoparticle": 0.05}, {}, 200000.0)
        approx(r["otherTermPa"], 0.0, 1e-12)

    def test_effective_nonpolymer_modulus_stiffens(self):
        r = ph.composite_shear_modulus(
            {"polymer": 0.62, "nanoparticle": 0.05}, {"nanoparticle": 10e6}, 200000.0)
        approx(r["shearPa"], 0.62 * 200000.0 + 0.05 * 10e6, 1e-6)

    def test_reports_every_phase(self):
        r = ph.composite_shear_modulus(
            {"polymer": 0.62, "nanoparticle": 0.05, "water": 0.33}, {}, 200000.0)
        assert [p["phase"] for p in r["phases"]] == list(ph.PHASES)
        approx(sum(p["phi"] for p in r["phases"]), 1.0, 1e-9)
