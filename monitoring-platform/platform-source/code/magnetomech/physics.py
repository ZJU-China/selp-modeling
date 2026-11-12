"""Magneto-elastic response of a GROMACS-CG SELP rubber loaded with magnetic
nanoparticles (modelled as spherical magnetite, Fe3O4).

The model (documented assumptions; estimates, not a fitted theory):

* Particles are superparamagnetic below their blocking temperature and follow
  a Langevin magnetization curve M(H) = Ms * L(xi), xi = mu0 * mp * H / (kB T),
  with the internal field reduced by the sample's demagnetizing factor Nd:
  H_int = H_app - Nd * phi * M(H_int), solved self-consistently.
* Particles formed into chains along the applied field interact through
  dipole attraction. The resulting magnetic energy density is
  u_m = (1/2) * k * phi * mu0 * M_p^2, where k is a coupling/alignment factor
  between 0 and 1 that absorbs partial chain alignment and transverse
  repulsion (default 0.25).
* The normal (compressive) stress along the field is u_m and the field-induced
  shear modulus change is estimated as dG = (3/4) * u_m (incompressible).
* The rubber is an incompressible neo-Hookean solid (nu = 0.5, E = 3G):
  eps_par = -sigma/E along the field and eps_perp = +sigma/(2E) transverse.
"""
import math

MU0 = 4.0 * math.pi * 1e-7  # H/m
KB = 1.380649e-23  # J/K
MS_FE3O4 = 4.8e5  # A/m (bulk magnetite saturation at ~300 K, ~92 emu/g)
RHO_FE3O4 = 5170.0  # kg/m^3
DEFAULT_DEMAG = 1.0 / 3.0
DEFAULT_COUPLING = 0.25


def langevin(x: float) -> float:
    """L(x) = coth(x) - 1/x, stable at x = 0 and in the saturated limit."""
    if abs(x) < 1e-6:
        return x / 3.0 - x ** 3 / 45.0
    if x > 50.0:
        return 1.0 - 1.0 / x
    if x < -50.0:
        return -1.0 - 1.0 / x
    return math.cosh(x) / math.sinh(x) - 1.0 / x


def particle_moment(ms: float, diameter_m: float) -> float:
    return ms * (math.pi / 6.0) * diameter_m ** 3


def magnetization(ms: float, diameter_m: float, field_h: float, temp_k: float) -> float:
    """Particle magnetization M_p (A/m) for an external field H (A/m)."""
    xi = MU0 * particle_moment(ms, diameter_m) * field_h / (KB * temp_k)
    return ms * langevin(xi)


def internal_field(applied_h: float, vol_frac: float, ms: float, diameter_m: float,
                   temp_k: float, demag: float = DEFAULT_DEMAG, iters: int = 80) -> float:
    """Self-consistent H_int = H_app - Nd * phi * M_p(H_int)."""
    if vol_frac <= 0.0:
        return applied_h
    h_int = applied_h
    for _ in range(iters):
        m = magnetization(ms, diameter_m, h_int, temp_k)
        h_int_new = applied_h - demag * vol_frac * m
        if abs(h_int_new - h_int) < abs(h_int) * 1e-9 + 1e-4:
            h_int = h_int_new
            break
        h_int = h_int_new
    return h_int


def magnetic_energy_density(particle_mag: float, vol_frac: float, coupling: float = DEFAULT_COUPLING) -> float:
    """u_m = (1/2) * k * phi * mu0 * M_p^2 (Pa)."""
    return 0.5 * coupling * vol_frac * MU0 * particle_mag ** 2


def magnetic_stress(particle_mag: float, vol_frac: float, coupling: float = DEFAULT_COUPLING) -> float:
    """Normal compressive stress along the field = u_m (Pa)."""
    return magnetic_energy_density(particle_mag, vol_frac, coupling)


def shear_modulus_change(particle_mag: float, vol_frac: float, coupling: float = DEFAULT_COUPLING) -> float:
    """Field-induced shear modulus increase dG (Pa)."""
    return 0.75 * magnetic_energy_density(particle_mag, vol_frac, coupling)


def axial_strain(sigma: float, young_pa):
    """Incompressible uniaxial strain along the applied field (negative =
    contraction because the dipole attraction compresses the chain)."""
    if not young_pa or young_pa <= 0.0:
        return 0.0
    return -sigma / young_pa


def transverse_strain(sigma: float, young_pa):
    """Poisson response nu = 0.5: eps_perp = -0.5 * eps_par."""
    return 0.5 * sigma / young_pa if young_pa and young_pa > 0.0 else 0.0


def composite_magnetization(particle_mag: float, vol_frac: float) -> float:
    """Macroscopic average magnetization of the composite M_eff = phi * M_p."""
    return vol_frac * particle_mag


def max_h_of_t(tesla: float) -> float:
    """Nominal applied field strength for a target flux density B = mu0 * H."""
    return tesla / MU0


def magnetization_curve(ms: float, diameter_m: float, temp_k: float,
                        h_max: float, n: int = 161) -> list:
    """M(H) curve for 0..H_max (returns [[h, m_p, xi], ...])."""
    out = []
    for i in range(n):
        h = h_max * i / (n - 1)
        xi = MU0 * particle_moment(ms, diameter_m) * h / (KB * temp_k)
        out.append([h, ms * langevin(xi), xi])
    return out

# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------
#
# The sample is three coexisting phases: the crosslinked polymer skeleton, the
# magnetic nanoparticles, and water. Water is the remainder, so only two volume
# fractions are independent:
#
#     phi_polymer + phi_nanoparticle + phi_water = 1
#
# Only the nanoparticles are magnetic, so every magnetic term above
# (magnetization, internal field, u_m) is driven by phi_nanoparticle alone. The
# polymer fraction acts through the stiffness of the loaded sample.
#
# Stiffness of the loaded sample.
#
# The CG network modulus is a property of the crosslinked polymer network as
# measured for that network, i.e. at unit polymer concentration. Diluting the
# polymer with the other phases means fewer strands between crosslinks, so the
# network carries proportionally less load and the sample softens:
#
#     G_eff = phi_polymer * G_network  +  sum_i phi_i * G_i^eff   (non-polymer)
#
# Linear scaling is the classical result for a network whose strand count is
# fixed and which is then swollen: the free energy density is N kT / V over the
# swollen volume, so the modulus falls with the polymer fraction.
#
# The non-polymer terms are opt-in via an *effective load-bearing* modulus and
# default to zero. That is deliberate: bulk magnetite is ~77 GPa, so folding its
# bulk modulus in at phi=0.05 would predict a ~3.9 GPa composite, which is
# meaningless for a sub-MPa elastomer -- a nanoparticle in a rubber does not
# carry load like a block of solid magnetite. Anyone who has a defensible
# effective value can supply it.
#
# An inverse/Reuss rule was tried here and rejected: it only normalises when
# every phase is load-bearing, so with water carrying nothing it *increased* the
# modulus as the polymer was diluted, inverting the physics.

# Effective load-bearing shear moduli (Pa) for the non-polymer phases. Zero
# means "carries no load" -- the safe default, see the note above.
DEFAULT_PHASE_SHEAR_PA = {
    "nanoparticle": 0.0,
    "water": 0.0,
}

PHASES = ("polymer", "nanoparticle", "water")


def water_fraction(phis: dict) -> float:
    """phi_water = 1 - sum(everything else)."""
    return 1.0 - sum(float(v or 0.0) for k, v in phis.items() if k != "water")


def composite_shear_modulus(phis: dict, phase_shear_pa: dict, polymer_shear_pa: float) -> dict:
    """Shear modulus of the loaded sample (Pa).

    G = phi_polymer * G_network + sum_i phi_i * G_i^eff  (non-polymer phases)
    """
    rows = []
    for name in PHASES:
        phi = float(phis.get(name) or 0.0)
        if name == "polymer":
            g = polymer_shear_pa
        else:
            g = float(phase_shear_pa.get(name, DEFAULT_PHASE_SHEAR_PA.get(name, 0.0)) or 0.0)
        rows.append({"phase": name, "phi": phi, "shearPa": g})

    polymer_term = float(phis.get("polymer") or 0.0) * polymer_shear_pa
    other_term = sum(r["phi"] * r["shearPa"] for r in rows if r["phase"] != "polymer")
    return {
        "shearPa": polymer_term + other_term,
        "polymerTermPa": polymer_term,
        "otherTermPa": other_term,
        "phases": rows,
    }
