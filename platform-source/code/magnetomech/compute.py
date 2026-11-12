"""End-to-end magneto-elastic computation.

Consumes a task-config-shaped ``params`` dict (see field.make_profile and
modulus.resolve_explicit_or_cg for the schema) and returns a JSON-serializable
result with:

* ``modulus``   CG-simulated Young's modulus + derived E/G (Pa).
* ``config``    normalized parameters (echoed for the UI).
* ``curves``    field sweep at uniform profile: H, M_p, M_eff, B, sigma, dG,
                E_eff, eps_par, eps_perp, dLL for H = 0..max_t.
* ``layers``    position-dependent response along the sample axis at max_t:
                z_m, H_app, M_p, B, sigma, eps_par, dispersion u_disp (mm) and
                transverse strain.
* ``summary``   headline numbers: max/at-B0 contraction percent, dG/G, E_eff,
                applied field B0, and the modulus source.
"""
import math
from . import physics as ph
from . import field as fld
from . import modulus as mod


def _r(x, digits=6):
    if x is None or x != x:  # NaN guard
        return None
    return round(float(x), digits)


def _point_response(h_app, vol_frac, ms, d_m, temp_k, demag, coupling, young_pa,
                    mag_needed=True):
    h_int = ph.internal_field(h_app, vol_frac, ms, d_m, temp_k, demag)
    m_p = ph.magnetization(ms, d_m, h_int, temp_k) if mag_needed else 0.0
    m_eff = ph.composite_magnetization(m_p, vol_frac)
    b_int = ph.MU0 * (h_int + m_eff)
    sigma = ph.magnetic_stress(m_p, vol_frac, coupling)
    dg = ph.shear_modulus_change(m_p, vol_frac, coupling)
    e_eff = young_pa + 3.0 * dg if young_pa is not None else None
    eps_par = ph.axial_strain(sigma, young_pa)
    eps_perp = ph.transverse_strain(sigma, young_pa)
    return {"h_int": h_int, "m_p": m_p, "m_eff": m_eff, "b_int": b_int,
            "sigma": sigma, "dg": dg, "e_eff": e_eff, "eps_par": eps_par,
            "eps_perp": eps_perp}


def field_curve(vol_frac, ms, d_m, temp_k, demag, coupling, young_pa, h_max, n=161):
    out = []
    for i in range(n):
        h_app = h_max * i / (n - 1)
        r = _point_response(h_app, vol_frac, ms, d_m, temp_k, demag, coupling, young_pa,
                            mag_needed=True)
        dll = r["eps_par"] if young_pa else 0.0
        out.append({
            "h": _r(h_app, 4), "t": _r(ph.MU0 * h_app, 6), "mP": _r(r["m_p"], 4),
            "mEff": _r(r["m_eff"], 4), "b": _r(r["b_int"], 6),
            "sigma": _r(r["sigma"], 6), "dG": _r(r["dg"], 6),
            "eEff": _r(r["e_eff"], 4) if r["e_eff"] is not None else None,
            "epsPar": _r(r["eps_par"], 8), "epsPerp": _r(r["eps_perp"], 8),
            "dLL": _r(dll, 8),
        })
    return out


def layer_response(profile, vol_frac, ms, d_m, temp_k, demag, coupling,
                   young_pa, height_m):
    layers = []
    disp = 0.0
    prev_eps = 0.0
    for i, (z, h_app) in enumerate(profile):
        r = _point_response(h_app, vol_frac, ms, d_m, temp_k, demag, coupling, young_pa,
                            mag_needed=True)
        dz = height_m / max(1, len(profile) - 1)
        if i == 0:
            step = 0.0
        else:
            step = 0.5 * (prev_eps + r["eps_par"]) * dz
        disp += step
        prev_eps = r["eps_par"]
        layers.append({
            "z": _r(z, 8), "h": _r(h_app, 4), "b": _r(r["b_int"], 6),
            "mP": _r(r["m_p"], 4), "sigma": _r(r["sigma"], 6),
            "epsPar": _r(r["eps_par"], 8), "uDisp": _r(disp * 1e3, 8),
        })
    return layers


def summarize(curves, layers, modulus, young_pa, h0, applied_b):
    if not curves:
        return {}
    last = curves[-1]
    eps_at_max = last["epsPar"] if last["epsPar"] is not None else 0.0
    dG_at_max = last["dG"] if last["dG"] is not None else 0.0
    dll_at_last = abs(last["dLL"]) if last["dLL"] is not None else 0.0
    max_dll = max((abs(c["dLL"]) for c in curves), default=0.0)
    g_base = young_pa / 3.0 if young_pa else None
    u_end_mm = abs(layers[-1]["uDisp"]) if layers else None
    return {
        # The peak field the sample actually sees. For a csv profile this is
        # read from the file, so it is not the config's maxT.
        "appliedBT": _r(applied_b, 4),
        "appliedHTop": _r(h0, 4),
        "epsParAtMax": _r(eps_at_max, 8),
        "contractionPctAtMax": _r(dll_at_last * 100.0, 4),
        "maxContractionPct": _r(max_dll * 100.0, 4),
        "dGAtMax": _r(dG_at_max, 6),
        "dGOverG": _r(dG_at_max / g_base, 6) if g_base else None,
        "eEffAtMaxPa": _r(last["eEff"], 4) if last["eEff"] is not None else None,
        "endDispMm": _r(u_end_mm, 6),
        "youngKpa": _r(young_pa / 1000.0, 4),
        "modulusSource": modulus["source"] if modulus else None,
        "modulusMode": modulus["mode"] if modulus else None,
    }


def resolve_composite(params, polymer_young_pa):
    """Resolve the composite, or None when the config has no "composite" block.

    Returning None is what preserves the original single-fraction behaviour
    exactly: a config that only sets particle.phi keeps using that value for both
    the magnetic terms and (via the CG modulus) the stiffness, with no
    composite mixing applied.
    """
    comp = params.get("composite")
    if not isinstance(comp, dict):
        return None
    species = comp.get("species") if isinstance(comp.get("species"), dict) else comp
    if not isinstance(species, dict):
        species = {}
    # An empty block is not a composite. Treating it as one would silently
    # replace the single-fraction stiffness with a zero-fraction one.
    if not any(v is not None for v in species.values()):
        return None

    def phi_of(name):
        raw = species.get(name)
        if isinstance(raw, dict):
            return raw.get("phi")
        return raw

    phis = {name: float(phi_of(name) or 0.0) for name in ph.PHASES}

    # Water is the remainder, so two fractions are independent. Recomputing it
    # here (rather than trusting a stored value) keeps the three from ever
    # summing to something other than 1. Only ph.PHASES is read, so a key naming
    # a phase the model does not have is ignored rather than silently counted.
    phis["water"] = ph.water_fraction({k: v for k, v in phis.items() if k != "water"})

    phase_shear = {}
    for name in ph.PHASES:
        if name == "polymer":
            continue
        raw = species.get(name)
        if isinstance(raw, dict) and raw.get("shearKpa") is not None:
            phase_shear[name] = float(raw["shearKpa"]) * 1000.0

    # Polymer shear from the network: incompressible, so E = 3G. The network
    # modulus is a unit-concentration property, so phi_polymer scales it.
    polymer_shear = float(polymer_young_pa) / 3.0
    mixed = ph.composite_shear_modulus(phis, phase_shear, polymer_shear)

    # Only the nanoparticles are magnetic, so the magnetic terms keep using the
    # nanoparticle fraction alone.
    return {
        "phis": phis,
        "phiTotal": sum(phis.values()),
        "polymerShearPa": polymer_shear,
        "phaseShearPa": phase_shear,
        "phases": mixed["phases"],
        "shearPa": mixed["shearPa"],
        "polymerTermPa": mixed["polymerTermPa"],
        "otherTermPa": mixed["otherTermPa"],
        "youngPa": mixed["shearPa"] * 3.0,   # incompressible composite
        "phiMagnetic": phis["nanoparticle"],
    }


def run(params):
    c = dict(params or {})
    mag = (c.get("particle") or {}).copy()
    vol_frac = float(mag.get("phi", 0.05))
    d_m = float(mag.get("diameterNm", 10.0)) * 1e-9
    ms = float(mag.get("saturationAperM", ph.MS_FE3O4))
    temp_k = float(c.get("temperatureK", 310.0))
    demag = float(c.get("demagFactor", ph.DEFAULT_DEMAG))
    coupling = float(c.get("coupling", ph.DEFAULT_COUPLING))
    field_cfg = (c.get("field") or {}) if isinstance(c.get("field"), dict) else {}
    field_mode = (field_cfg.get("mode") or c.get("fieldMode") or "uniform").lower()
    max_t = float(field_cfg.get("maxT", 0.6))
    if field_mode == "csv":
        field_cfg = dict(field_cfg, csvPath=field_cfg.get("csvPath") or c.get("csvPath"))
    try:
        modulus = mod.resolve_explicit_or_cg(c.get("magnetomech", c))
    except (FileNotFoundError, ValueError) as e:
        modulus = {"source": "error: %s" % e, "mode": "error", "kpa": None,
                   "pa": None, "phantomKpa": None, "affineKpa": None,
                   "scanlanAffineKpa": None, "note": str(e), "temperatureK": None,
                   "volumeNm3": None}
    modulus_pa = modulus.get("pa")
    young_pa = float(modulus_pa) if modulus_pa is not None else 0.0

    # A composite block replaces the single-fraction stiffness and points the
    # magnetic terms at the nanoparticle fraction. Without one, vol_frac and
    # young_pa keep their original values untouched.
    composite = resolve_composite(c, young_pa)
    if composite is not None:
        young_pa = float(composite["youngPa"])
        vol_frac = float(composite["phiMagnetic"])
    height_m = float(field_cfg.get("heightM") or 0.0) or (float(field_cfg.get("heightMm") or 10.0) / 1e3)
    n_points = int(field_cfg.get("nPoints") or 201)

    profile = fld.make_profile(field_mode, dict(field_cfg, heightMm=height_m * 1e3))
    # The sweep has to reach the strongest field anywhere in the sample, not the
    # field at its first point: a gradient rises with z and a profile read from
    # a CSV is ordered by position, so profile[0] is the weakest point and would
    # cap the sweep below the peak the layers actually experience.
    h_peak = max((h for _, h in profile), default=0.0)
    h0 = h_peak
    curves = field_curve(vol_frac, ms, d_m, temp_k, demag, coupling, young_pa,
                         h0, n=161)
    layers = layer_response(profile, vol_frac, ms, d_m, temp_k, demag, coupling,
                            young_pa, height_m)
    summary = summarize(curves, layers, modulus, young_pa, h0, ph.MU0 * h_peak)

    config = {
        "modulusMode": modulus.get("mode"),
        "modulusKpa": _r(modulus.get("kpa"), 4),
        "volFracPhi": _r(vol_frac, 6),
        "particleDiameterNm": _r(d_m * 1e9, 4),
        "saturationAperM": _r(ms, 4),
        "temperatureK": _r(temp_k, 4),
        "demagFactor": _r(demag, 4),
        "coupling": _r(coupling, 4),
        "fieldMode": field_mode,
        "maxT": _r(max_t, 4),
        "heightMm": _r(height_m * 1e3, 4),
        "nPoints": n_points,
        "csvPath": field_cfg.get("csvPath"),
        "composite": composite,
        # The loaded-sample modulus actually used, and where it came from, so a
        # composite result is never mistaken for the bare CG network value.
        "effectiveYoungKpa": _r(young_pa / 1000.0, 4),
        "effectiveYoungSource": "composite" if composite else "cg-network",
    }
    return {"modulus": modulus, "config": config, "curves": curves,
            "layers": layers, "summary": summary}


def write_result(result, out_dir):
    import csv as _csv
    import json as _json
    import os
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "magnetomech.summary.json"), "w", encoding="utf-8") as f:
        _json.dump(result, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "magnetomech.curve.csv"), "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["h_AperM", "t_T", "Mp_AperM", "MEff_AperM", "B_T", "sigma_Pa", "dG_Pa",
                    "eEff_Pa", "epsPar", "epsPerp", "dLL"])
        for c in result["curves"]:
            w.writerow([c["h"], c["t"], c["mP"], c["mEff"], c["b"], c["sigma"], c["dG"],
                        c["eEff"] if c["eEff"] is not None else "", c["epsPar"],
                        c["epsPerp"], c["dLL"]])
    with open(os.path.join(out_dir, "magnetomech.layer.csv"), "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["z_m", "H_AperM", "B_T", "Mp_AperM", "sigma_Pa", "epsPar", "uDisp_mm"])
        for c in result["layers"]:
            w.writerow([c["z"], c["h"], c["b"], c["mP"], c["sigma"], c["epsPar"], c["uDisp"]])
    return result["summary"]