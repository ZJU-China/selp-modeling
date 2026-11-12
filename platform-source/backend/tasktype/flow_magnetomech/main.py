#!/usr/bin/env python3
"""
flow_magnetomech -- magnetomech with an editable field file.

This merges the field/parameter preparation into the magnetomech compute task so
the composite fractions and the applied field are inputs the user fills in on
the Parameters panel rather than values buried in scripts/task_config.json.

What it generates from the panel inputs:

  input/field_profile.csv  the resolved applied-field profile actually used,
                           written out so what the compute saw can be inspected
                           (and checked against an uploaded file) without
                           reading the code
  input/params.json        the resolved parameters, including the composite
                           fractions with water recomputed as the remainder

Composition is three coexisting phases -- polymer, nanoparticle, water -- with
only two fractions independent:

    phi_polymer + phi_nanoparticle + phi_water = 1

water is the remainder, so it is recomputed here rather than trusted from the
config. Only the nanoparticles are magnetic, so every magnetic term uses
phi_nanoparticle alone; the polymer fraction acts through the loaded-sample
stiffness (see code/magnetomech/physics.py).

Field modes mirror code/magnetomech/field.py: "uniform" and "gradient" generate
the profile, while "csv" reads an uploaded profile whose header needs a position
column (z or x) and a field column (b or h). An uploaded file that has neither is
rejected at synthesize time with the columns it did find, because
load_csv_profile would otherwise silently fall through to an empty profile and
the run would quietly report a zero field.

Usage mirrors magnetomech/main.py:

    flow_magnetomech/main.py magnetomech --local-dir DIR --task-config CFG
    flow_magnetomech/main.py synthesize  --local-dir DIR [--task-config CFG]

`synthesize` writes the two files above and stops. `magnetomech` synthesizes first,
so editing the fractions or the field and recomputing regenerates them rather
than reusing a stale file, then delegates to magnetomech/main.py.
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TASKTYPE_DIR = os.path.dirname(HERE)
MAGNETOMECH_MAIN = os.path.join(TASKTYPE_DIR, "magnetomech", "main.py")

PHASES = ("polymer", "nanoparticle", "water")

# field.py looks the header up case-insensitively by exact name. The _mm variant
# is listed separately because load_csv_profile reads a bare z/x as metres while
# the panel collects the sample height in millimetres.
POSITION_COLUMNS = ("z", "x")
MM_POSITION_COLUMNS = ("z_mm", "x_mm", "position_mm")
FIELD_COLUMNS = ("b", "h")


def read_config(path):
    if not path:
        return {}
    try:
        with open(path) as f:
            return json.load(f) or {}
    except Exception:
        return {}


def first(*values):
    for v in values:
        if v is not None and str(v).strip() != "":
            return v
    return None


def as_float(value, default=0.0):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def resolve_composite(config):
    """The fractions, with water recomputed as the remainder."""
    comp = config.get("composite")
    species = {}
    if isinstance(comp, dict):
        raw = comp.get("species") if isinstance(comp.get("species"), dict) else comp
        if isinstance(raw, dict):
            for name in PHASES:
                entry = raw.get(name)
                if isinstance(entry, dict):
                    species[name] = entry.get("phi")
                elif entry is not None:
                    species[name] = entry
    phis = {name: as_float(species.get(name), 0.0) for name in PHASES}
    phis["water"] = 1.0 - sum(phis[p] for p in PHASES if p != "water")
    return phis


def csv_header_columns(path, limit=64):
    """Column names of a CSV, lowercased, as field.py would read them."""
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        header = f.readline()
    return [c.strip().lower() for c in header.split(",") if c.strip()]


def csv_column(path, name):
    """One column's numeric values, by header name."""
    import csv as _csv
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = _csv.reader(f)
        try:
            header = [c.strip().lower() for c in next(reader)]
        except StopIteration:
            return []
        if name not in header:
            return []
        idx = header.index(name)
        out = []
        for row in reader:
            if len(row) <= idx:
                continue
            try:
                out.append(float(row[idx]))
            except ValueError:
                continue
        return out


def check_field_csv(path, height_mm=0.0):
    """Verify an uploaded profile is one load_csv_profile can actually use.

    Returns (ok, message). load_csv_profile skips rows it cannot read and clamps
    outside the file's own range, so a bad header or mismatched position units
    would otherwise turn into a run that reports a nearly flat or zero field.
    """
    if not os.path.isfile(path):
        return False, "Field file not found: %s" % os.path.basename(path)
    try:
        cols = csv_header_columns(path)
    except OSError as e:
        return False, "Could not read the field file: %s" % e
    if not cols:
        return False, "The field file is empty."
    has_pos_mm = next((c for c in cols if c in MM_POSITION_COLUMNS), None)
    has_pos = has_pos_mm or next((c for c in cols if c in POSITION_COLUMNS), None)
    has_field = next((c for c in cols if c in FIELD_COLUMNS), None)
    if not has_pos:
        return False, ("The field file needs a position column named %s (metres) or %s "
                       "(millimetres). Columns found: %s"
                       % (" or ".join(POSITION_COLUMNS), MM_POSITION_COLUMNS[0], ", ".join(cols)))
    if not has_field:
        return False, ("The field file needs a field column named %s. Columns found: %s"
                       % (" or ".join(FIELD_COLUMNS), ", ".join(cols)))
    if height_mm > 0.0:
        positions = csv_column(path, has_pos)
        if positions:
            scale = 1e-3 if has_pos_mm else 1.0
            lo, hi = min(positions) * scale, max(positions) * scale
            height_m = height_mm / 1e3
            tol = max(1e-12, height_m * 1e-3)
            # Either failure mode gives a silently wrong profile: a file that
            # stops short of the sample clamps to its nearest end, and a file
            # spanning far beyond it contributes only its first few rows, so the
            # rest of the sample reads as one constant. The second case is what
            # millimetres read as metres looks like.
            span = (lo * 1e3, hi * 1e3)
            if lo > height_m + tol or hi < height_m - tol:
                return False, (
                    "The field file positions span %.4f..%.4f mm, which does not cover "
                    "the sample (0..%g mm); a profile taken from another origin cannot "
                    "be applied to this sample." % (span[0], span[1], height_mm))
            if hi > height_m * 100.0:
                return False, (
                    "The field file positions span %.4f..%.4f mm but the sample is only "
                    "%g mm tall, so the applied profile would be wrong.%s"
                    % (span[0], span[1], height_mm,
                       "" if has_pos_mm else
                       " Rename the column to %s if these values are millimetres."
                       % MM_POSITION_COLUMNS[0]))
    return True, ("position column '%s'%s, field column '%s'"
                  % (has_pos, " (mm)" if has_pos_mm else "", has_field))


def resolve_field_profile(config, local_dir):
    """Reproduce the profile field.py would build, for inspection.

    Kept deliberately simple: this is a record of what was applied, not the
    physics. The compute interpolates the uploaded file onto the sample grid
    itself (field.load_csv_profile).
    """
    field_cfg = config.get("field") or {}
    mode = str(field_cfg.get("mode") or "uniform").lower()
    height_mm = as_float(field_cfg.get("heightMm"), 10.0)
    n_points = int(as_float(field_cfg.get("nPoints"), 201)) or 201
    max_t = as_float(field_cfg.get("maxT"), 0.6)
    delta_t = as_float(field_cfg.get("gradientDeltaT"), 0.2)

    rows = []
    if mode == "gradient":
        # field.gradient_profile: maxT at z=0 rising by deltaT over the height.
        # Sign and end matter -- this file is the record of what was applied, so
        # writing it the other way round would misstate the field.
        for i in range(n_points):
            z = height_mm * i / (n_points - 1) if n_points > 1 else 0.0
            rows.append([z, max_t + delta_t * (z / height_mm if height_mm else 0.0)])
    elif mode == "uniform":
        for i in range(n_points):
            z = height_mm * i / (n_points - 1) if n_points > 1 else 0.0
            rows.append([z, max_t])
    return mode, rows


def synthesize(local_dir, config):
    """Write the resolved field profile and parameters. Returns a result dict;
    never raises for user-fixable input, so the caller can report precisely."""
    input_dir = os.path.join(local_dir, "input")
    os.makedirs(input_dir, exist_ok=True)

    phis = resolve_composite(config)
    field_cfg = config.get("field") or {}
    mode = str(field_cfg.get("mode") or "uniform").lower()

    if phis["water"] < -1e-9:
        return {
            "ok": False,
            "stage": "composite",
            "error": "The two fractions add up to %.4f, leaving %.4f for water. "
                     "Their sum must not exceed 1."
                     % (sum(phis[p] for p in PHASES if p != "water"), phis["water"]),
        }

    # A csv-mode run is only meaningful with a usable file, so check the header
    # before computing rather than letting load_csv_profile return nothing.
    csv_name = str(field_cfg.get("csvPath") or "").strip()
    field_note = None
    if mode == "csv":
        if not csv_name:
            return {
                "ok": False,
                "stage": "field",
                "error": "Field mode is \"csv\" but no field file is set. Upload a profile "
                         "CSV, or switch the mode back to uniform/gradient.",
            }
        candidates = []
        if os.path.isabs(csv_name):
            candidates.append(csv_name)
        else:
            # The panel stores the task-relative path it uploaded to
            # (input/<name>), so try local_dir first or that becomes
            # input/input/<name>. Then a bare filename, then the path as the
            # caller meant it from their own working directory.
            candidates.append(os.path.join(local_dir, csv_name))
            candidates.append(os.path.join(input_dir, csv_name))
            candidates.append(csv_name)
        resolved = next((c for c in candidates if os.path.isfile(c)), None)
        if resolved is None:
            return {
                "ok": False,
                "stage": "field",
                "error": "Field file %r was not found in this task's input/." % csv_name,
            }
        ok, note = check_field_csv(resolved, as_float(field_cfg.get("heightMm"), 10.0))
        if not ok:
            return {"ok": False, "stage": "field", "error": note}
        field_note = note

    mode_used, rows = resolve_field_profile(config, local_dir)
    profile_rel = os.path.join("input", "field_profile.csv")
    with open(os.path.join(local_dir, profile_rel), "w", newline="", encoding="utf-8") as f:
        w = _csv_writer(f)
        w.writerow(["z_mm", "B_T"])
        for z, b in rows:
            w.writerow(["%.6f" % z, "%.6f" % b])
        if mode == "csv":
            # Keep the uploaded profile in the same file so the record is
            # complete rather than pointing elsewhere.
            w.writerow([])
            w.writerow(["# uploaded field file: %s" % csv_name])
            if field_note:
                w.writerow(["# %s" % field_note])

    params_rel = os.path.join("input", "params.json")
    resolved_params = {
        "composite": {"phis": phis, "phiTotal": sum(phis.values())},
        "field": {
            "mode": mode_used,
            "maxT": as_float(field_cfg.get("maxT"), 0.6),
            "gradientDeltaT": as_float(field_cfg.get("gradientDeltaT"), 0.2),
            "heightMm": as_float(field_cfg.get("heightMm"), 10.0),
            "nPoints": int(as_float(field_cfg.get("nPoints"), 201)),
            "csvPath": csv_name or None,
        },
        "particle": config.get("particle") or {},
        "magnetomech": config.get("magnetomech") or {},
        "temperatureK": as_float(first(config.get("temperatureK"), 310.0), 310.0),
        "coupling": as_float(first(config.get("coupling"), 0.25), 0.25),
        "demagFactor": as_float(first(config.get("demagFactor"), 1.0 / 3.0), 1.0 / 3.0),
    }
    with open(os.path.join(local_dir, params_rel), "w", encoding="utf-8") as f:
        json.dump(resolved_params, f, ensure_ascii=False, indent=2)
        f.write("\n")

    return {
        "ok": True,
        "phis": phis,
        "phiTotal": sum(phis.values()),
        "fieldMode": mode_used,
        "fieldFile": csv_name or None,
        "fieldNote": field_note,
        "profile": profile_rel,
        "params": params_rel,
        "profilePoints": len(rows),
    }


def _csv_writer(f):
    import csv as _csv
    return _csv.writer(f)


def build_arg_parser():
    # Mirror magnetomech/main.py so delegation passes argv through unchanged.
    # --host/--user are accepted but never used: magnetomech is local compute.
    p = argparse.ArgumentParser(description="flow_magnetomech: magnetomech with an editable field file")
    p.add_argument("command", nargs="?", default="status", choices=[
        "synthesize", "magnetomech",
        "status", "checkpoint", "progress", "monitor", "stop", "restart", "start",
        "route", "log-paths", "structure", "cluster", "gen-trajectory",
        "convergence-check",
    ])
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=22)
    p.add_argument("--user", default=None)
    p.add_argument("--key", default=None)
    p.add_argument("--password", default=None)
    p.add_argument("--local-dir", default=None)
    p.add_argument("--task-config", default=None)
    p.add_argument("--remote-dir", default=None)
    p.add_argument("--log-prefix", default=None)
    p.add_argument("--num-replicas", type=int, default=None)
    p.add_argument("--steps-per-cycle", type=int, default=None)
    p.add_argument("--total-cycles", type=float, default=None)
    p.add_argument("--phi", default=None)
    return p


def main():
    args = build_arg_parser().parse_args()
    config = read_config(args.task_config)
    local_dir = args.local_dir or os.getcwd()

    if args.command == "synthesize":
        result = synthesize(local_dir, config)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    if args.command == "magnetomech":
        # Regenerate from the current panel inputs first, so editing the
        # fractions or the field and recomputing cannot reuse a stale profile.
        result = synthesize(local_dir, config)
        if not result.get("ok"):
            print(json.dumps(result, ensure_ascii=False))
            return 1
        print(json.dumps({"synthesized": result}, ensure_ascii=False), file=sys.stderr)

    return subprocess.call([sys.executable, MAGNETOMECH_MAIN] + sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
