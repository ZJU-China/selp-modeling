"""Local path + task_config resolution for a GROMACS CG task's analysis.

Everything here is a pure filesystem helper (no MDAnalysis/numpy), so it is
safe to unit-test with the system interpreter.
"""
import json
import os
import re
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from _shared.config_lookup import value_lookup

DEFAULT_STEPS_PER_CYCLE = 500000
DEFAULT_DT_FS = 20
DEFAULT_NUM_REPLICAS = 1

_RE_DCD = re.compile(r"replica_(\d+)\.dcd$")

_CFG_CANDIDATES = ("input", "scripts", "data", "")


def analysis_dir(task_dir):
    return os.path.join(task_dir, "cache", "analysis")


def trajectory_dir(task_dir):
    return os.path.join(task_dir, "cache", "trajectory")


def output_dir(task_dir):
    return os.path.join(task_dir, "output")


def load_task_config(task_dir):
    """Read scripts/task_config.json defaults (stepsPerCycle, timestepFs, ...).

    Returns an always-populated dict plus the raw config under `raw`.
    """
    raw = {}
    path = os.path.join(task_dir, "scripts", "task_config.json")
    try:
        with open(path) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        pass
    # Flat top-level values (saved by the Flow Console parameter panel) win over
    # `defaults`, so the analysis converts the same trajectory length the run
    # actually used.
    d = value_lookup(raw)

    return {
        "stepsPerCycle": d.int_("stepsPerCycle", DEFAULT_STEPS_PER_CYCLE),
        "timestepFs": d.int_("timestepFs", DEFAULT_DT_FS),
        "numReplicas": d.int_("numReplicas", DEFAULT_NUM_REPLICAS),
        "totalCycles": d.float_("totalCycles", 10),
        "raw": raw,
    }


def _dcd_index(filename):
    m = _RE_DCD.match(filename)
    if m is None:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def discover_dcds(traj_dir):
    """sorted cache/trajectory/replica_<i>.dcd files (replica index order)."""
    paths = []
    try:
        for f in os.listdir(traj_dir):
            idx = _dcd_index(f)
            if idx is not None:
                paths.append((idx, os.path.join(traj_dir, f)))
    except OSError:
        return []
    paths.sort(key=lambda p: p[0])
    return [p for _, p in paths]


def discover_samples(out_dir):
    """Sorted sample directory names under output/."""
    try:
        return sorted(d for d in os.listdir(out_dir)
                      if os.path.isdir(os.path.join(out_dir, d)))
    except OSError:
        return []


def topology_path(traj_dir):
    p = os.path.join(traj_dir, "topology.pdb")
    return p if os.path.isfile(p) else None


def gro_path(out_dir, sample):
    p = os.path.join(out_dir, sample, "relax.gro")
    return p if os.path.isfile(p) else None


def xtc_path(out_dir, sample):
    p = os.path.join(out_dir, sample, "relax.xtc")
    return p if os.path.isfile(p) else None


def edr_path(out_dir, sample):
    p = os.path.join(out_dir, sample, "relax.edr")
    return p if os.path.isfile(p) else None


def mdlog_path(out_dir, sample):
    for name in ("relax.log", "md.log", "gromacs.log"):
        p = os.path.join(out_dir, sample, name)
        if os.path.isfile(p):
            return p
    return None


def find_task_file(task_dir, names):
    """Locate one of `names` under the standard task sub dirs.

    Returns the first existing path (task input/scripts/data/ root order), or
    None. Used for the handoff artifacts (network.json, crosslink_pairs.tsv).
    """
    for base in ("input", "scripts", "data", ""):
        for name in names:
            p = os.path.join(task_dir, base, name) if base else os.path.join(task_dir, name)
            if os.path.isfile(p):
                return p
    return None


def network_json_path(task_dir):
    return find_task_file(task_dir, ("network.json",))


def crosslink_tsv_path(task_dir):
    return find_task_file(task_dir, ("crosslink_pairs.tsv", "crosslinks.tsv"))