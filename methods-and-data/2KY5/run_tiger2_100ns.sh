#!/usr/bin/env bash
set -euo pipefail

NAMD_DIR=${NAMD_DIR:-/home/selp/igem-2026/FAMD/NAMD_3.0.2_Linux-x86_64-netlrts-smp}
PROCESSES=${PROCESSES:-4}
PPN=${PPN:-3}
mkdir -p production/{0,1,2,3}
exec "$NAMD_DIR/charmrun" "$NAMD_DIR/namd3" \
    ++local ++n "$PROCESSES" ++ppn "$PPN" +replicas 4 tiger2_100ns_each.conf \
    +stdout 'production/%d/tiger2_2ky5_snoopytag.%d.log'
