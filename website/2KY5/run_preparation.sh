#!/usr/bin/env bash
set -euo pipefail

NAMD=${NAMD:-/home/selp/igem-2026/FAMD/NAMD_3.0.2_Linux-x86_64-multicore/namd3}
THREADS=${THREADS:-12}

mkdir -p equil logs

run_stage() {
    local conf=$1
    local root="equil/${conf%.conf}"
    local log="logs/${conf%.conf}.log"
    if [[ -s "${root}.coor" ]] && grep -q 'End of program' "$log" 2>/dev/null; then
        echo "[$(date '+%F %T')] skipping completed $conf"
        return
    fi
    echo "[$(date '+%F %T')] starting $conf"
    "$NAMD" "+p${THREADS}" "$conf" > "$log" 2>&1
    if grep -Eqi 'FATAL ERROR|ERROR:|nan|constraint failure|moving too fast|Segmentation' "$log"; then
        echo "ERROR detected in $log"
        grep -Ein 'FATAL ERROR|ERROR:|nan|constraint failure|moving too fast|Segmentation' "$log" | tail -20
        exit 1
    fi
    grep -q 'End of program' "$log"
    echo "[$(date '+%F %T')] completed $conf"
}

run_stage 01_minimize_vacuum.conf
run_stage 02_minimize_gbis.conf
run_stage 03_gbis_warm_025fs.conf
run_stage 04_gbis_eq_050fs.conf
run_stage 05_gbis_eq_1fs.conf
run_stage 06_gbis_eq_2fs.conf
run_stage 07_gbis_eq_4fs.conf

echo "PREPARATION_OK"
