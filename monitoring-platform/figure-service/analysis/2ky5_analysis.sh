#!/usr/bin/env bash
# Rebuild the analysis XVG files for the 2KY-5 flow tasks.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-/home/selp/CG_2KY5_batch_crosslinks_20261006}"
OUT="${OUT:-$HERE/rebuilt/2ky5}"
mkdir -p "$OUT"
python3 "$HERE/rebuild_xvg.py" --dir "$ROOT/joint_stability_2ky5_to2ns_20261012/A_relax2000" --out "$OUT/cg_A_relax2000"
