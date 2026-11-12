#!/usr/bin/env bash
# Rebuild the analysis XVG files for the 2KY-16 flow tasks.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-/home/selp/CG_2KY5_batch_crosslinks_20261006}"
OUT="${OUT:-$HERE/rebuilt/2ky16}"
mkdir -p "$OUT"
python3 "$HERE/rebuild_xvg.py" --dir "$ROOT/2KY16_prediction_20261018/network_sampling/A_relax4000" --out "$OUT/cg_A_relax4000"
