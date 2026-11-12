#!/usr/bin/env bash
###############################################################################
# tiger2_run.sh — TIGER2-REMD 启动/重启/状态/停止管理脚本
#
# 用法:
#   ./tiger2_run.sh start              从 equilibration 全新启动
#   ./tiger2_run.sh restart [CYCLE]    从最近/指定 cycle 的 checkpoint 重启
#   ./tiger2_run.sh status             查看运行状态与进度
#   ./tiger2_run.sh stop               停止运行中的模拟
#   ./tiger2_run.sh logs [N]           查看 replica 0 的日志 (默认最后50行)
#   ./tiger2_run.sh detect             列出所有可用 checkpoint
#
# 环境要求:
#   - screen 已安装 (apt install screen)
#   - NAMD 3.0 netlrts-smp 版本位于 NAMD_DIR
#
# 注意: 不要在裸 SSH session 中直接运行 NAMD, 必须使用本脚本的 screen
#       或自行使用 tmux, 以防止 SSH 断开导致进程被杀。
###############################################################################
set -euo pipefail

# ── 配置 ─────────────────────────────────────────────────────────────────────
TIGER2_DIR="$(cd "$(dirname "$0")" && pwd)"
NAMD_DIR="${NAMD_DIR:-../NAMD_3.0.2_Linux-x86_64-netlrts-smp}"
NPROCS="${NPROCS:-4}"          # charmrun ++n (总进程数)
PPN="${PPN:-1}"                # charmrun ++ppn (每进程核心数)
NREPLICAS="${NREPLICAS:-4}"    # replica 数量
CONF_FILE="tiger2_100ns.conf"  # 主配置
NAMD_BIN="${NAMD_DIR}/namd3"
CHARM="${NAMD_DIR}/charmrun"
SCREEN_NAME="tiger2"
LOG_DIR="${TIGER2_DIR}/production"
STATUS_PY="${TIGER2_DIR}/../gen_sim_status.py"  # 状态生成脚本

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "${CYAN}[STEP]${NC}  $*"; }

# ── 前置检查 ─────────────────────────────────────────────────────────────────
preflight() {
    if [[ ! -x "$NAMD_BIN" ]]; then
        error "NAMD not found at $NAMD_BIN"
        exit 1
    fi
    if ! command -v screen &>/dev/null; then
        error "screen not found. Install: sudo apt install screen"
        exit 1
    fi
    cd "$TIGER2_DIR"
}

# ── 检测最新 checkpoint ──────────────────────────────────────────────────────
# 扫描所有 replica 的 restart 文件, 返回最大的 cycle 编号和对应的 job_id
detect_latest_checkpoint() {
    local max_cycle=-1 max_job=0
    for r in $(seq 0 $((NREPLICAS - 1))); do
        local dir="${LOG_DIR}/${r}"
        # 匹配 tiger2-prod.job{N}.restart{cycle}.{R}.{coor|tcl}
        for f in "$dir"/tiger2-prod.job*.restart*.${r}.tcl; do
            [[ -f "$f" ]] || continue
            local basename
            basename=$(basename "$f")
            # 提取 job_id 和 cycle: tiger2-prod.job3.restart350.0.tcl
            local job cycle
            job=$(echo "$basename" | sed -n 's/.*job\([0-9]*\)\.restart.*/\1/p')
            cycle=$(echo "$basename" | sed -n 's/.*restart\([0-9]*\)\..*/\1/p')
            if [[ -n "$job" && -n "$cycle" && "$cycle" -gt "$max_cycle" ]]; then
                max_cycle=$cycle
                max_job=$job
            fi
        done
    done
    echo "$max_cycle $max_job"
}

# ── 生成 restart 配置文件 ────────────────────────────────────────────────────
generate_restart_conf() {
    local cycle=$1
    local job_id=$2
    local conf="tiger2_continue_${cycle}.conf"

    # 如果已存在且内容正确, 不重新生成
    if [[ -f "$conf" ]]; then
        local existing_job
        existing_job=$(grep -oP 'restart350' "$conf" 2>/dev/null | head -1 || true)
        # 检查 restart_name 中的 cycle 是否匹配
        if grep -q "restart${cycle}" "$conf" 2>/dev/null; then
            info "Config $conf already exists"
            return 0
        fi
    fi

    cat > "$conf" <<EOF
set restart_name production/%s/tiger2-prod.job${job_id}.restart${cycle}
source ./${CONF_FILE}
EOF
    info "Generated $conf"
}

# ── 检查所有 replica 的 checkpoint 文件是否齐全 ──────────────────────────────
verify_checkpoint() {
    local cycle=$1
    local job_id=$2
    local ok=0
    for r in $(seq 0 $((NREPLICAS - 1))); do
        local base="${LOG_DIR}/${r}/tiger2-prod.job${job_id}.restart${cycle}"
        local missing=0
        for ext in tcl coor vel xsc; do
            [[ -f "${base}.${r}.${ext}" ]] || missing=1
        done
        if [[ $missing -eq 1 ]]; then
            warn "Replica $r: missing checkpoint files at cycle $cycle"
        else
            ok=$((ok + 1))
        fi
    done
    if [[ $ok -eq $NREPLICAS ]]; then
        info "All $NREPLICAS replicas have valid checkpoints at cycle $cycle"
        return 0
    else
        error "Only $ok/$NREPLICAS replicas have valid checkpoints"
        return 1
    fi
}

# ── 启动 (screen 内) ─────────────────────────────────────────────────────────
launch_namd() {
    local conf=$1
    local run_label=$2

    # 确保 screen 未被占用
    if screen -list | grep -q "$SCREEN_NAME"; then
        error "Screen session '$SCREEN_NAME' already exists."
        echo "  Use: screen -r $SCREEN_NAME  (to attach)"
        echo "  Or:  ./tiger2_run.sh stop  (to kill it)"
        exit 1
    fi

    local run_cmd="${CHARM} ${NAMD_BIN} ++local ++n ${NPROCS} ++ppn ${PPN} +replicas ${NREPLICAS} ${conf} +stdout '${LOG_DIR}/%d/tiger2_continue_%s.%d.log'"

    step "Launching in screen '$SCREEN_NAME'..."
    screen -dmS "$SCREEN_NAME" bash -c "
        cd ${TIGER2_DIR}
        echo \"[\$(date)] TIGER2 ${run_label} started\" | tee /tmp/tiger2_screen.log
        echo \"Config: ${conf}\" | tee -a /tmp/tiger2_screen.log
        echo \"Command: ${run_cmd}\" | tee -a /tmp/tiger2_screen.log
        echo '---' | tee -a /tmp/tiger2_screen.log
        ${run_cmd} 2>&1 | tee -a /tmp/tiger2_screen.log
        EXIT_CODE=\${PIPESTATUS[0]}
        echo '---' | tee -a /tmp/tiger2_screen.log
        echo \"[\$(date)] NAMD exited with code \${EXIT_CODE}\" | tee -a /tmp/tiger2_screen.log
        sleep 86400
    "
    info "Screen session '$SCREEN_NAME' started (detached)"
    echo ""
    echo "  查看:  screen -r $SCREEN_NAME"
    echo "  后台:  Ctrl-A, D (在 screen 内)"
    echo "  日志:  tail -f /tmp/tiger2_screen.log"
    echo "  状态:  ./tiger2_run.sh status"
}

# ── 子命令: start ────────────────────────────────────────────────────────────
cmd_start() {
    info "=== TIGER2 Fresh Start ==="
    preflight

    # 检查是否已有运行中的实例
    if pgrep -f 'namd3.*tiger2' >/dev/null 2>&1; then
        warn "NAMD processes already running (from other session?)"
        pgrep -af 'namd3.*tiger2' || true
        read -r -p "Continue anyway? [y/N] " yn
        [[ "${yn,,}" == "y" ]] || exit 0
    fi

    # 检查是否已有 restart 文件 (可能之前跑过)
    local cycle job_id
    read -r cycle job_id <<< "$(detect_latest_checkpoint)"
    if [[ $cycle -gt 0 ]]; then
        warn "Found existing checkpoint at cycle $cycle (job${job_id})"
        echo "  Use './tiger2_run.sh restart $cycle' to resume from it"
        read -r -p "Start fresh (overwrite existing output)? [y/N] " yn
        [[ "${yn,,}" == "y" ]] || exit 0
    fi

    mkdir -p production/{0,1,2,3}

    # 检查 equilibration 文件
    local eq_coor="input/hmr4fs_eq100ps.coor"
    if [[ ! -f "$eq_coor" ]]; then
        error "Equilibration coordinate not found: $eq_coor"
        exit 1
    fi

    step "Checking config..."
    if [[ ! -f "$CONF_FILE" ]]; then
        error "Config $CONF_FILE not found"
        exit 1
    fi

    step "Starting NAMD from equilibration..."
    launch_namd "$CONF_FILE" "fresh start"
}

# ── 子命令: restart ──────────────────────────────────────────────────────────
cmd_restart() {
    info "=== TIGER2 Restart ==="
    preflight

    local target_cycle="${1:-}"
    local cycle job_id

    if [[ -n "$target_cycle" ]]; then
        # 用户指定了 cycle, 查找对应的 job_id
        cycle=$target_cycle
        job_id=-1
        for r in $(seq 0 $((NREPLICAS - 1))); do
            for f in "${LOG_DIR}/${r}"/tiger2-prod.job*.restart${cycle}.${r}.tcl; do
                if [[ -f "$f" ]]; then
                    job_id=$(basename "$f" | sed -n 's/.*job\([0-9]*\)\.restart.*/\1/p')
                    break 2
                fi
            done
        done
        if [[ $job_id -lt 0 ]]; then
            error "No checkpoint found at cycle $cycle"
            echo ""
            cmd_detect
            exit 1
        fi
    else
        # 自动检测最新 checkpoint
        read -r cycle job_id <<< "$(detect_latest_checkpoint)"
        if [[ $cycle -lt 0 ]]; then
            error "No checkpoint files found. Use './tiger2_run.sh start' for fresh start."
            exit 1
        fi
    fi

    info "Restarting from cycle $cycle (job${job_id})"
    verify_checkpoint "$cycle" "$job_id" || exit 1

    generate_restart_conf "$cycle" "$job_id"

    local conf="tiger2_continue_${cycle}.conf"

    # 检查是否已有运行中的实例
    if pgrep -f 'namd3.*tiger2' >/dev/null 2>&1; then
        warn "NAMD processes detected:"
        pgrep -af 'namd3.*tiger2' || true
        read -r -p "Kill existing and restart? [y/N] " yn
        if [[ "${yn,,}" == "y" ]]; then
            cmd_stop
            sleep 2
        else
            exit 0
        fi
    fi

    if screen -list | grep -q "$SCREEN_NAME"; then
        warn "Screen session '$SCREEN_NAME' exists. Killing..."
        screen -S "$SCREEN_NAME" -X quit 2>/dev/null || true
        sleep 1
    fi

    step "Launching NAMD from cycle $cycle..."
    launch_namd "$conf" "restart from cycle ${cycle}"
}

# ── 子命令: status ───────────────────────────────────────────────────────────
cmd_status() {
    preflight

    info "=== TIGER2 Simulation Status ==="
    echo ""

    # 运行状态
    if pgrep -f 'namd3.*tiger2' >/dev/null 2>&1; then
        echo -e "  Process:  ${GREEN}RUNNING${NC}"
        local nproc
        nproc=$(pgrep -c -f 'namd3.*tiger2' 2>/dev/null || echo 0)
        echo "  Workers:  $nproc processes"
        if screen -list 2>/dev/null | grep -q "$SCREEN_NAME"; then
            echo "  Screen:   $SCREEN_NAME (attached)"
        fi
    else
        echo -e "  Process:  ${RED}NOT RUNNING${NC}"
        # 检查是否是正常退出
        if [[ -f /tmp/tiger2_screen.log ]]; then
            local last_line
            last_line=$(grep "NAMD exited" /tmp/tiger2_screen.log 2>/dev/null | tail -1 || true)
            if [[ -n "$last_line" ]]; then
                echo "  Last log: $last_line"
            fi
        fi
    fi
    echo ""

    # Checkpoint 信息
    local cycle job_id
    read -r cycle job_id <<< "$(detect_latest_checkpoint)"
    if [[ $cycle -ge 0 ]]; then
        echo "  Latest checkpoint:  cycle $cycle (job${job_id})"
    else
        echo "  Latest checkpoint:  none"
    fi
    echo ""

    # 从日志中读取当前进度
    local latest_step=0
    local latest_energy_line=""
    for r in 0; do  # 只看 replica 0
        local log_dir="${LOG_DIR}/${r}"
        for log in "$log_dir"/tiger2_continue_*.${r}.log "$log_dir"/tiger2_prod.${r}.log; do
            [[ -f "$log" ]] || continue
            local last_energy
            last_energy=$(grep -a "^ENERGY:" "$log" | tail -1 || true)
            if [[ -n "$last_energy" ]]; then
                local step
                step=$(echo "$last_energy" | awk '{print $2}')
                if [[ "$step" -gt "$latest_step" ]]; then
                    latest_step=$step
                    latest_energy_line=$last_energy
                fi
            fi
        done
    done

    if [[ $latest_step -gt 0 ]]; then
        local total_steps=$((417 * 15000))  # num_runs * steps_sample
        local pct=$(printf "%.1f" "$(echo "scale=4; $latest_step * 100 / $total_steps" | bc 2>/dev/null || echo 0)")
        local run_num=$(echo "scale=0; $latest_step / 15000" | bc 2>/dev/null || echo 0)
        local remaining_days=$(printf "%.2f" "$(echo "scale=4; (417 - $run_num) * 0.06 / 24" | bc 2>/dev/null || echo 0)")
        echo "  Current step:      $latest_step / $total_steps"
        echo "  Progress:          ${pct}% (run ${run_num}/417)"
        echo "  Estimated time left: ${remaining_days} days (~$(echo "scale=0; $remaining_days * 24" | bc)h)"
        echo ""
        echo "  Last ENERGY line (replica 0):"
        echo "    $latest_energy_line"
    else
        echo "  No ENERGY output found yet."
    fi

    # gen_sim_status 输出
    # 注意: gen_sim_status.py 的 running 检测可能误报 (pgrep 匹配 SSH 查询命令)
    if [[ -f "$STATUS_PY" ]]; then
        echo ""
        echo "  --- gen_sim_status.py output ---"
        python3 "$STATUS_PY" "$TIGER2_DIR" "/tmp/tiger2_sim_status.json" 2>/dev/null || true
        if [[ -f /tmp/tiger2_sim_status.json ]]; then
            python3 -c "
import json
with open('/tmp/tiger2_sim_status.json') as f:
    d = json.load(f)
r = d.get('replicas', {})
total_wall = max((v.get('wall_time_s', 0) for v in r.values()), default=0)
print(f'  Total wall time:  {total_wall/3600:.1f} h')
print(f'  Replicas ready:   {len(r)}/4')
for rid, rv in sorted(r.items()):
    s = rv.get('last_step', 0)
    print(f'    Replica {rid}: step {s} ({rv.get(\"total_frames\", 0)} frames)')
" 2>/dev/null || true
        fi
    fi
}

# ── 子命令: stop ─────────────────────────────────────────────────────────────
cmd_stop() {
    info "Stopping TIGER2..."

    # 先杀 NAMD 进程
    if pgrep -f 'namd3.*tiger2' >/dev/null 2>&1; then
        warn "Killing NAMD processes..."
        pkill -f 'namd3.*tiger2' 2>/dev/null || true
        sleep 2
        # 强杀残余
        pkill -9 -f 'namd3.*tiger2' 2>/dev/null || true
    fi

    # 再杀 charmrun
    if pgrep -f 'charmrun.*tiger2' >/dev/null 2>&1; then
        pkill -f 'charmrun.*tiger2' 2>/dev/null || true
        sleep 1
    fi

    # 关闭 screen session
    if screen -list 2>/dev/null | grep -q "$SCREEN_NAME"; then
        screen -S "$SCREEN_NAME" -X quit 2>/dev/null || true
        info "Screen session '$SCREEN_NAME' killed"
    fi

    # 确认
    sleep 1
    if pgrep -f 'namd3.*tiger2' >/dev/null 2>&1; then
        error "Some processes still running:"
        pgrep -af 'namd3.*tiger2' || true
    else
        info "All TIGER2 processes stopped"
    fi

    # 保存当前状态
    echo ""
    info "Current progress:"
    cmd_status 2>/dev/null || true
}

# ── 子命令: logs ─────────────────────────────────────────────────────────────
cmd_logs() {
    local lines="${1:-50}"
    preflight

    info "=== Replica 0 logs (last $lines lines) ==="

    # 优先看 screen 日志
    if [[ -f /tmp/tiger2_screen.log ]]; then
        echo ""
        echo "--- Screen log ---"
        tail -"$lines" /tmp/tiger2_screen.log
    fi

    # 找最新的 NAMD 日志
    local latest_log=""
    local latest_mtime=0
    for log in "${LOG_DIR}/0"/tiger2_continue_*.0.log "${LOG_DIR}/0"/tiger2_prod.0.log; do
        [[ -f "$log" ]] || continue
        local mt
        mt=$(stat -c %Y "$log" 2>/dev/null || echo 0)
        if [[ "$mt" -gt "$latest_mtime" ]]; then
            latest_mtime=$mt
            latest_log=$log
        fi
    done

    if [[ -n "$latest_log" ]]; then
        echo ""
        echo "--- NAMD log: $latest_log ---"
        tail -"$lines" "$latest_log"
    else
        warn "No NAMD log files found"
    fi
}

# ── 子命令: detect ───────────────────────────────────────────────────────────
cmd_detect() {
    preflight

    info "=== Available Checkpoints ==="
    echo ""

    for r in $(seq 0 $((NREPLICAS - 1))); do
        echo "Replica $r:"
        local dir="${LOG_DIR}/${r}"
        for f in "$dir"/tiger2-prod.job*.restart*.${r}.tcl; do
            [[ -f "$f" ]] || continue
            local basename job_id cycle
            basename=$(basename "$f" .tcl)
            job_id=$(echo "$basename" | sed -n 's/.*job\([0-9]*\)\.restart.*/\1/p')
            cycle=$(echo "$basename" | sed -n 's/.*restart\([0-9]*\)\..*/\1/p')
            local coor="${dir}/tiger2-prod.job${job_id}.restart${cycle}.${r}.coor"
            local ok="OK"
            [[ -f "$coor" ]] || ok="MISSING coor"
            printf "  job%s restart%-4s  step %-10s  [%s]\n" "$job_id" "$cycle" "$((cycle * 15000))" "$ok"
        done
        echo ""
    done
}

# ── 主入口 ───────────────────────────────────────────────────────────────────
usage() {
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  start              Fresh start from equilibration"
    echo "  restart [CYCLE]    Restart from checkpoint (auto-detect latest if no cycle)"
    echo "  status             Show simulation status and progress"
    echo "  stop               Kill running simulation"
    echo "  logs [N]           Show last N lines of logs (default: 50)"
    echo "  detect             List all available checkpoints"
    echo ""
    echo "Environment variables:"
    echo "  NAMD_DIR   NAMD binary directory (default: ../NAMD_3.0.2_Linux-x86_64-netlrts-smp)"
    echo "  NPROCS     Total processes (default: 4)"
    echo "  PPN        Processes per node (default: 1)"
    echo "  NREPLICAS  Number of replicas (default: 4)"
}

main() {
    local cmd="${1:-}"
    shift || true

    case "$cmd" in
        start)   cmd_start ;;
        restart) cmd_restart "$@" ;;
        status)  cmd_status ;;
        stop)    cmd_stop ;;
        logs)    cmd_logs "$@" ;;
        detect)  cmd_detect ;;
        -h|--help|"")  usage ;;
        *)
            error "Unknown command: $cmd"
            usage
            exit 1
            ;;
    esac
}

main "$@"
