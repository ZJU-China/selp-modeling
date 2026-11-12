#!/usr/bin/env bash
# Rebuild the analysis XVG files for the 2KY-10 flow tasks.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${ROOT:-/home/selp/CG_2KY5_batch_crosslinks_20261006}"
OUT="${OUT:-$HERE/rebuilt/2ky10}"
mkdir -p "$OUT"
python3 "$HERE/rebuild_xvg.py" --dir "$ROOT/joint_stability_both_to4ns_20261013/2KY10_A_relax4000" --out "$OUT/cg_A_relax4000"
if [ "${SKIP_MECH:-0}" != "1" ]; then
  for d in "$ROOT"/joint_stability_both_to4ns_20261013/2KY10_*; do
    [ -d "$d" ] || continue
    python3 "$HERE/rebuild_xvg.py" --dir "$d" --out "$OUT/mech/$(basename "$d")"
  done
fi
