"""Rubber-elasticity modulus analysis for a GROMACS CG task's own network.

Single-network analysis: reads ``input/network.json`` (the task's own CG
network), the temperature from ``modulus.temperatureK`` (default 310 K) and the
box volume from ``cache/analysis/box.dat`` (mean relax.gro box volume, the
per-task CG result; falls back to ``modulus.volumeNm3``).  It then runs the
shared network32 rubber-elasticity analyzer on that one network and writes the
result in the exact ensemble schema the magnetomech tasktype consumes
(``assumptions`` + ``ensemble`` + ``networks``), so the downstream magnetomech
step can pick the modulus straight off the flow handoff.

Writes:
  cache/analysis/rubber_elasticity_summary.json
  output/rubber_elasticity_summary.json   (flow handoff to magnetomech)

The network32.rubber analyzer is pure stdlib (json/math/collections), so this
module never needs MDAnalysis/numpy; only the CG src path is required.
"""
import json
import math
import os
import sys
from pathlib import Path

from . import paths, writers

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# lib/analysis -> lib -> tasktype dir -> tasktype -> backend -> repo root.
_TASKTYPE_DIR = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_TASKTYPE_DIR, "..", "..", ".."))
_CG_SRC = os.path.join(_REPO_ROOT, "CG", "CG_platform_handoff_20260907", "src")

DEFAULT_TEMPERATURE_K = 310.0

# The single-network run is exactly one member of an ensemble, so the ensemble
# of one network reproduces write_ensemble_outputs' schema (magnetomech reads
# ensemble.young_incompressible_*).
_METRIC_NAMES = (
    "kpa_per_mode",
    "phantom_cycle_kpa",
    "chemical_crosslink_kpa",
    "scanlan_case_phantom_kpa",
    "scanlan_case_empirical_2x_phantom_kpa",
    "scanlan_case_affine_kpa",
    "affine_kpa",
)


def _import_network32_rubber():
    if not os.path.isdir(_CG_SRC):
        raise ImportError("CG network32 src not found at %s" % _CG_SRC)
    if _CG_SRC not in sys.path:
        sys.path.insert(0, _CG_SRC)
    from network32 import rubber  # noqa: F401
    return rubber


def _read_cfg(cfg):
    raw = cfg.get("raw") or {}
    modulus_cfg = raw.get("modulus") or {}
    return modulus_cfg


def _temperature_k(cfg):
    modulus_cfg = _read_cfg(cfg)
    try:
        t = float(modulus_cfg.get("temperatureK", DEFAULT_TEMPERATURE_K))
    except (TypeError, ValueError):
        t = DEFAULT_TEMPERATURE_K
    return t if t > 0 else DEFAULT_TEMPERATURE_K


def _mean_box_volume_nm3(task_dir):
    """Mean relax.gro box volume (nm^3) from cache/analysis/box.dat.

    box.dat rows: ``replica step box_x(nm) box_y(nm) box_z(nm)``; volume of a
    cubic (or orthorhombic) box is x*y*z averaged over every logged frame.
    Returns None when the file is missing or unreadable so callers can fall
    back to the configured volume.
    """
    path = os.path.join(paths.analysis_dir(task_dir), "box.dat")
    if not os.path.isfile(path):
        return None
    volumes = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                fields = line.split()
                if len(fields) < 5:
                    continue
                try:
                    x, y, z = (float(fields[i]) for i in (2, 3, 4))
                except ValueError:
                    continue
                if x > 0 and y > 0 and z > 0:
                    volumes.append(x * y * z)
    except OSError:
        return None
    return sum(volumes) / len(volumes) if volumes else None


def _volume_nm3(task_dir, cfg):
    modulus_cfg = _read_cfg(cfg)
    configured = modulus_cfg.get("volumeNm3")
    if configured not in (None, ""):
        try:
            v = float(configured)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    box = _mean_box_volume_nm3(task_dir)
    if box and box > 0:
        return box
    return None


def _build_summary(result, temperature_k, volume_nm3):
    modulus = result["modulus"]
    ensemble = {name: modulus.get(name) for name in _METRIC_NAMES}
    ensemble["network_count"] = 1
    ensemble["young_incompressible_phantom_kpa"] = 3.0 * ensemble["phantom_cycle_kpa"]
    ensemble["young_incompressible_scanlan_case_affine_kpa"] = (
        3.0 * ensemble["scanlan_case_affine_kpa"]
    )
    ensemble["young_incompressible_affine_kpa"] = 3.0 * ensemble["affine_kpa"]
    ensemble["note"] = (
        "The phantom-to-affine interval is a model bound, not a statistical "
        "confidence interval. Single-network run of the task's input/network.json."
    )
    return {
        "assumptions": {
            "temperature_k": temperature_k,
            "volume_nm3": volume_nm3,
            "affine_modes": "polymer segments between adjacent Tyr crosslink junctions",
            "phantom_modes": "effective superstrands minus effective junctions after iterative periodic Scanlan-Case reduction",
            "finite_cycle_rank_retained_as_reference_only": True,
            "dangling_terminal_tails_excluded": True,
            "source_network": result.get("network"),
        },
        "ensemble": ensemble,
        "networks": [result],
    }


def analyze(task_dir, cfg):
    net_path = paths.network_json_path(task_dir)
    if not net_path:
        return {"ok": False, "error": "no input/network.json for modulus analysis"}
    temperature_k = _temperature_k(cfg)
    volume_nm3 = _volume_nm3(task_dir, cfg)
    if not volume_nm3:
        return {"ok": False, "error": "no box volume (cache/analysis/box.dat or modulus.volumeNm3)"}
    try:
        rubber = _import_network32_rubber()
    except ImportError as e:
        return {"ok": False, "error": f"network32 unavailable: {e}"}
    try:
        result = rubber.analyze_network_json(
            Path(net_path), temperature_k=temperature_k, volume_nm3=volume_nm3)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    summary = _build_summary(result, temperature_k, volume_nm3)

    analysis = paths.analysis_dir(task_dir)
    os.makedirs(analysis, exist_ok=True)
    cache_path = os.path.join(analysis, "rubber_elasticity_summary.json")
    writers.write_json(cache_path, summary)

    # Flow handoff: expose the summary through output/ so the flow-<prev>
    # symlink lets a downstream magnetomech task read it as input/flow-*/.
    out = paths.output_dir(task_dir)
    os.makedirs(out, exist_ok=True)
    output_path = os.path.join(out, "rubber_elasticity_summary.json")
    writers.write_json(output_path, summary)

    return {
        "ok": True,
        "source": net_path,
        "temperature_k": temperature_k,
        "volume_nm3": volume_nm3,
        "temperature_k_source": "config" if _read_cfg(cfg).get("temperatureK") not in (None, "") else "default",
        "volume_source": "box.dat" if "volumeNm3" not in _read_cfg(cfg) else "config",
        "network": result.get("network"),
        "n_chains": result.get("n_chains"),
        "chemical_crosslinks": result.get("chemical_crosslinks"),
        "affine_kpa": summary["ensemble"]["affine_kpa"],
        "young_incompressible_affine_kpa": summary["ensemble"]["young_incompressible_affine_kpa"],
        "output": output_path,
    }