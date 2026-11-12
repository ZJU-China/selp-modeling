"""Reading the GROMACS CG (network32) rubber Young's modulus.

The platform characterizes each candidate CG network with phantom-network and
affine-network rubber elasticity (see CG/CG_platform_handoff_20260907/src/
network32/rubber.py).  The canonical result lives in
artifacts/periodic_modulus_32chain/rubber_elasticity/rubber_elasticity_summary.json.
"""
import json
import math
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CG_SUMMARY = REPO_ROOT / "CG" / "CG_platform_handoff_20260907" / "artifacts" / \
    "periodic_modulus_32chain" / "rubber_elasticity" / "rubber_elasticity_summary.json"

MODES = {
    "affine": "young_incompressible_affine_kpa",
    "phantom": "young_incompressible_phantom_kpa",
    "scanlan_affine": "young_incompressible_scanlan_case_affine_kpa",
}


def _kpa_to_pa(kpa):
    try:
        return float(kpa) * 1000.0
    except (TypeError, ValueError):
        return None


def load_cg_modulus(path=None, mode="affine"):
    """Return the CG-simulated Young's modulus dict.

    mode: ``affine`` (fully-crosslinked network, the upper model bound) is the
    default; ``phantom`` (effective superstrand network) is the lower bound and
    ``scanlan_affine`` the Scanlan-case affine estimate.
    """
    path = Path(path) if path else DEFAULT_CG_SUMMARY
    if not path.is_file():
        raise FileNotFoundError("CG rubber elasticity summary not found at %s" % path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    ens = data.get("ensemble", {})
    key = MODES.get(mode)
    if not key or not ens:
        raise ValueError("unsupported modulus mode %r or empty summary" % mode)
    kpa = ens.get(key)
    if kpa is None:
        raise ValueError("modulus key %s missing from %s" % (key, path))
    return {
        "source": str(path),
        "mode": mode,
        "kpa": float(kpa),
        "pa": _kpa_to_pa(kpa),
        "phantomKpa": float(ens["young_incompressible_phantom_kpa"]) if "young_incompressible_phantom_kpa" in ens else None,
        "affineKpa": float(ens["young_incompressible_affine_kpa"]) if "young_incompressible_affine_kpa" in ens else None,
        "scanlanAffineKpa": float(ens["young_incompressible_scanlan_case_affine_kpa"]) if "young_incompressible_scanlan_case_affine_kpa" in ens else None,
        "note": ens.get("note") or (data.get("assumptions", {}) or {}).get("affine_modes"),
        "temperatureK": (data.get("assumptions", {}) or {}).get("temperature_k"),
        "volumeNm3": (data.get("assumptions", {}) or {}).get("volume_nm3"),
    }


def resolve_explicit_or_cg(params):
    """Pick the Young's modulus (Pa) from a task-config dict.

    Priority: explicit ``modulusKpa`` > ``modulusPath`` > the repo CG summary
    (``modulusMode`` selects affine/phantom/scanlan_affine).
    """
    mode = (params.get("modulusMode") or "affine").lower()
    explicit = params.get("modulusKpa")
    if explicit is not None and not math.isnan(float(explicit)):
        value = float(explicit)
        if value > 0:
            return {"source": "explicit", "mode": "explicit", "kpa": value,
                    "pa": value * 1000.0, "phantomKpa": None, "affineKpa": None,
                    "scanlanAffineKpa": None, "note": "explicitly provided", "temperatureK": None,
                    "volumeNm3": None}
    cg = load_cg_modulus(params.get("modulusPath"), mode)
    return cg