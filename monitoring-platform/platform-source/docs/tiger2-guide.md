# TIGER2-REMD 启动与重启指南

## 目录结构

```
TIGER2_2KY10/
├── tiger2_100ns.conf          # 主配置 (417 cycles, 60 ps/cycle, 4 replicas)
├── tiger2_base.namd           # NAMD 底层设置 (GBIS, HMR, 4fs timestep)
├── tiger2_2ky10.namd          # TIGER2 Tcl 逻辑 (温度交换, restart 处理)
├── tiger2_run.sh              # 统一管理脚本 (本文档核心)
├── input/
│   ├── 2KY10_built.pdb       # 拓扑结构
│   ├── 2KY10_hmr.psf         # HMR 处理后的拓扑
│   └── hmr4fs_eq100ps.coor   # 4fs 平衡后坐标
├── production/
│   ├── 0/  1/  2/  3/        # 4 个 replica 的输出
│   │   ├── tiger2-prod.job{N}.restart{C}.{R}.coor  # 坐标 checkpoint
│   │   ├── tiger2-prod.job{N}.restart{C}.{R}.vel   # 速度 checkpoint
│   │   ├── tiger2-prod.job{N}.restart{C}.{R}.xsc   # 单位胞 checkpoint
│   │   ├── tiger2-prod.job{N}.restart{C}.{R}.tcl   # TIGER2 状态 checkpoint
│   │   └── tiger2_continue_*.R.log                  # NAMD 日志
│   └── analysis/             # 聚类分析输出
├── analysis/                 # Rg, E2E, RMSD, SS, 聚类结果
└── ../NAMD_3.0.2_Linux-x86_64-netlrts-smp/  # NAMD 二进制
```

## 快速开始

```bash
cd ~/igem-2026/MD/TIGER2_2KY10

# 全新启动 (从 equilibration 坐标)
./tiger2_run.sh start

# 从最新 checkpoint 自动重启
./tiger2_run.sh restart

# 从指定 cycle 重启
./tiger2_run.sh restart 350

# 查看状态
./tiger2_run.sh status

# 停止
./tiger2_run.sh stop

# 查看日志
./tiger2_run.sh logs 100
```

## 为什么需要 screen

SSH 断开时, 该 session 下的所有子进程都会收到 SIGHUP 并被杀掉。之前 TIGER2 多次因 SSH 超时而中断就是这个原因。

**使用 `screen` 隔离进程**: screen 会创建一个独立的终端 session, 即使 SSH 断开, 其中的进程也不会收到 SIGHUP。

```bash
# 本脚本自动处理 screen, 也可以手动:
screen -S tiger2                     # 创建
screen -r tiger2                     # 重新连接
# 在 screen 内: Ctrl-A, D           # 分离 (detach)
screen -ls                           # 列出所有 session
screen -X -S tiger2 quit             # 杀掉 session
```

## Checkpoint 机制

### 文件命名

```
production/{replica}/tiger2-prod.job{job_id}.restart{cycle}.{replica_id}.{ext}
```

| 字段 | 含义 |
|------|------|
| `job_id` | TIGER2 job 编号 (每 ~100 cycles 递增) |
| `cycle` | 循环编号 (0–416) |
| `replica_id` | replica 编号 (0–3) |
| `ext` | `tcl`(TIGER2 状态) / `coor`(坐标) / `vel`(速度) / `xsc`(单位胞) |

### Job 编号规则

| Job | Cycle 范围 | 步数范围 |
|-----|-----------|----------|
| job1 | 0–99 | 0–1,485,000 |
| job2 | 100–199 | 1,500,000–2,985,000 |
| job3 | 200–299 | 3,000,000–4,485,000 |
| job4 | 300–416 | 4,500,000–6,240,000 |

### 配置 restart_name

NAMD/TIGER2 restart 必须通过 config 文件中的 `set restart_name` 来指定, **不能** 通过 CLI 参数 `+restart_name` 传递 (会被 NAMD RTS 拒绝)。

```tcl
# tiger2_continue_350.conf 示例
set restart_name production/%s/tiger2-prod.job3.restart350
source ./tiger2_100ns.conf
```

`%s` 会被 TIGER2 Tcl 代码替换为 replica 编号。

## 常见操作

### 手动 SSH 后查看状态

```bash
ssh igem
cd ~/igem-2026/MD/TIGER2_2KY10
./tiger2_run.sh status
```

### 断线后重连

```bash
ssh igem
screen -r tiger2                    # 重连到运行中的 session
# 或
./tiger2_run.sh status              # 仅查看, 不连接
```

### 手动启动 (不使用脚本)

```bash
ssh igem
screen -S tiger2
cd ~/igem-2026/MD/TIGER2_2KY10

# 创建 restart 配置
cat > tiger2_continue_350.conf << 'EOF'
set restart_name production/%s/tiger2-prod.job3.restart350
source ./tiger2_100ns.conf
EOF

# 启动 NAMD
NAMD_DIR=../NAMD_3.0.2_Linux-x86_64-netlrts-smp
$NAMD_DIR/charmrun $NAMD_DIR/namd3 \
  ++local ++n 4 ++ppn 1 +replicas 4 tiger2_continue_350.conf \
  +stdout 'production/%d/tiger2_continue_%s.%d.log'

# Ctrl-A, D 分离
```

### 检查 checkpoint 完整性

```bash
./tiger2_run.sh detect
```

## NAMD 版本说明

| 版本 | 路径 | 用途 |
|------|------|------|
| netlrts-smp | `NAMD_3.0.2_Linux-x86_64-netlrts-smp` | TIGER2 REMD (必须用此版本) |
| netlrts-smp-HIP | `NAMD_3.0.2_Linux-x86_64-netlrts-smp-HIP` | GPU 加速 REMD (ROCm) |
| multicore | `NAMD_3.0.2_Linux-x86_64-multicore` | 单节点 MD (不支持 +replicas) |

**重要**: multicore 版本不支持 `+replicas` 参数, TIGER2 REMD 必须使用 netlrts-smp 版本。

## 故障排查

### Q: 进程莫名消失

原因: SSH 断开导致 SIGHUP 传播。

解决: 始终使用 `./tiger2_run.sh start/restart` 通过 screen 启动。

### Q: "restart with wrong number of replicas"

原因: `+replicas N` 与 config 中的 `set num_replicas N` 不匹配。

解决: 确保两者一致 (默认都是 4)。

### Q: "NO RESTART FILE"

NAMD 信息级日志, 不影响运行。TIGER2 的 restart 机制通过 `set restart_name` 处理, 与 NAMD 原生 restart 不同。

### Q: 检测到 "RUNNING" 但实际没有 namd3 进程

`gen_sim_status.py` 的 `pgrep -f 'namd3.*tiger2'` 会匹配包含 "namd3" 的其他进程 (如 SSH 查询命令), 导致误报。直接用 `pgrep -af namd3` 确认。

### Q: 进程占用 100% CPU 但步进不前进

检查日志中是否有 `ERROR` 或 `FATAL`。如果卡住, `./tiger2_run.sh stop` 然后 `restart`。

## 运行参数

| 参数 | 值 | 说明 |
|------|-----|------|
| replicas | 4 | 温度 replica 数 |
| temperature range | 280–400 K | 几何分布 |
| cycles | 417 | 总循环数 |
| steps/cycle | 15,000 | 每 cycle MD 步数 |
| timestep | 4 fs | HMR 处理后 |
| cycle time | 60 ps | 15,000 × 4 fs |
| total time/replica | 25.02 ns | 417 × 60 ps |
| total time (aggregate) | 100.08 ns | 4 × 25.02 ns |
| wall time per cycle | ~10 min | 4 replica 并行 |
| estimated total wall | ~70 h | ~2.9 天 |
