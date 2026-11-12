#!/usr/bin/env python3
"""Run the magneto-elastic computation and (optionally) write artifacts.

Usage:
    python3 run.py --config params.json [--output out_dir] [CLI overrides...]

The config is a task-config-shaped dict whose "magnetomech", "particle" and
"field" sections hold the parameters (see code/magnetomech/compute.run).  All
values may be overridden from the command line:

    --modulus-kpa 25             explicit modulus override (kPa)
    --modulus-mode affine|phantom|scanlan_affine
    --phi 0.05                   particle volume fraction
    --diameter-nm 10
    --temp-k 310
    --max-t 0.6                  applied field (T)
    --field-mode uniform|gradient|csv
    --coupling 0.25
    --csv-path path.csv
    --height-mm 10

Writes out_dir/{magnetomech.summary.json,magnetomech.curve.csv,
magnetomech.layer.csv,final_simulation.png} when --output is given and prints a
single JSON object (ok + summary + config + modulus) to stdout so the backend
can parse it. final_simulation.png is the backend-rendered chart the frontend
shows as the task's final simulation image.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from magnetomech import compute
from magnetomech.render import render_final_image


def parse_args():
    p = argparse.ArgumentParser(description="magnetomech CLI")
    p.add_argument("--config", default=None, help="JSON params file")
    p.add_argument("--output", default=None, help="output directory for artifacts")
    p.add_argument("--modulus-kpa", type=float, default=None)
    p.add_argument("--modulus-mode", default=None)
    p.add_argument("--phi", type=float, default=None)
    p.add_argument("--diameter-nm", type=float, default=None)
    p.add_argument("--temp-k", type=float, default=None)
    p.add_argument("--max-t", type=float, default=None)
    p.add_argument("--field-mode", default=None)
    p.add_argument("--coupling", type=float, default=None)
    p.add_argument("--csv-path", default=None)
    p.add_argument("--height-mm", type=float, default=None)
    return p.parse_args()


def apply_overrides(params, args):
    mag = dict(params.get("particle") or {})
    field_cfg = dict(params.get("field") or {})
    if args.modulus_kpa is not None:
        params["magnetomech"] = dict(params.get("magnetomech") or {},
                                     modulusKpa=args.modulus_kpa,
                                     modulusMode="explicit")
    if args.modulus_mode is not None:
        params["magnetomech"] = dict(params.get("magnetomech") or {},
                                     modulusMode=args.modulus_mode)
    if args.phi is not None:
        mag["phi"] = args.phi
    if args.diameter_nm is not None:
        mag["diameterNm"] = args.diameter_nm
    if args.temp_k is not None:
        params["temperatureK"] = args.temp_k
    if args.max_t is not None:
        field_cfg["maxT"] = args.max_t
    if args.field_mode is not None:
        field_cfg["mode"] = args.field_mode
    if args.csv_path is not None:
        field_cfg["csvPath"] = args.csv_path
    if args.height_mm is not None:
        field_cfg["heightMm"] = args.height_mm
    if args.coupling is not None:
        params["coupling"] = args.coupling
    if mag:
        params["particle"] = mag
    if field_cfg:
        params["field"] = field_cfg
    return params


def main():
    args = parse_args()
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            params = json.load(f)
    else:
        params = {}
    params = apply_overrides(params, args)
    result = compute.run(params)
    if args.output:
        summary = compute.write_result(result, args.output)
        image = render_final_image(result, args.output)
    else:
        summary = result["summary"]
        image = None
    print(json.dumps({"ok": True, "summary": summary,
                      "config": result["config"], "modulus": result["modulus"],
                      "nCurves": len(result["curves"]),
                      "nLayers": len(result["layers"]),
                      "image": image}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())