# Molecular Dynamics Platform 工作流程

## 总览

```
阶段 1          阶段 2          阶段 3          阶段 4          阶段 5          阶段 6
结构构建   →   能量最小化  →   HMR 处理    →   4fs 平衡    →   TIGER2 生产 →   分析聚类
   │               │               │               │               │               │
 build_psf.tcl  minimize.conf   make_hmr.tcl  hmr4fs_test    tiger2_100ns    python 脚本
                 hmr4fs_eq100ps
```

---

## 阶段 1: 结构构建

### 1.1 输入
- `2KY10.pdb` — Chimera 生成的初始伸展结构

### 1.2 运行
```bash
cd ~/igem-2026/MD
vmd -dispdev text -e scripts/tcl/build_2KY10_psf.tcl > build_psf.log 2>&1
```

### 1.3 输出
- `2KY10_built.psf` — 完整拓扑 (9563 atoms)
- `2KY10_built.pdb` — 匹配坐标

### 1.4 检查
```bash
grep '!NATOM' 2KY10_built.psf          # 应为 9563
grep -E '^(ATOM|HETATM)' 2KY10_built.pdb | wc -l  # 应为 9563
grep -Ei 'error|failed|unknown' build_psf.log
```

---

## 阶段 2: 能量最小化

### 2.1 输入
- `2KY10_built.psf` + `2KY10_built.pdb`

### 2.2 运行
```bash
namd3 +p16 scripts/namd/minimize.conf > minimize.log 2>&1
```

### 2.3 输出
- `minimize.coor` — 最小化后坐标
- `minimize.log` — 能量日志

### 2.4 检查
```bash
tail -5 minimize.log                    # 应有 "End of program"
grep -Ei 'FATAL ERROR|nan|Segmentation' minimize.log
awk '/^ENERGY:/ {print $2,$12}' minimize.log | tail -5  # 能量应下降
```

---

## 阶段 3: HMR 处理

### 3.1 运行
```bash
vmd -dispdev text -e scripts/tcl/make_hmr.tcl > make_hmr.log 2>&1
```

### 3.2 输出
- `2KY10_hmr.psf` — HMR 拓扑 (氢质量 3.024 Da)

### 3.3 检查
```bash
grep '!NATOM' 2KY10_built.psf 2KY10_hmr.psf  # 原子数相同
# 总质量检查 (应相同 ~67696.8 Da)
awk '/!NATOM/{n=$1;next} n>0{s+=$8;n--} END{print s}' 2KY10_built.psf
awk '/!NATOM/{n=$1;next} n>0{s+=$8;n--} END{print s}' 2KY10_hmr.psf
```

---

## 阶段 4: 4fs 测试与平衡

### 4.1 稳定性测试 (10 ps)
```bash
# 需要先有 minimize.coor
namd3 +p16 scripts/namd/hmr4fs_test.conf > hmr4fs_test.log 2>&1
```
**检查**: 无 fatal/nan/constraint failure

### 4.2 平衡 (100 ps)
```bash
namd3 +p16 scripts/namd/hmr4fs_eq100ps.conf > hmr4fs_eq100ps.log 2>&1
```
**输出**: `hmr4fs_eq100ps.coor` — TIGER2 起始坐标

### 4.3 检查
```bash
grep -Ei 'FATAL ERROR|nan|moving too fast' hmr4fs_eq100ps.log
awk '/^ENERGY:/ {s+=$13;n++} END {print "Avg temp:",s/n,"K"}' hmr4fs_eq100ps.log
# 应接近 280 K
```

---

## 阶段 5: TIGER2 模拟

### 5.0 准备输入目录
```bash
cd ~/igem-2026/MD/TIGER2_2KY10
mkdir -p input production/{0,1,2,3}
cp ../2KY10_hmr.psf input/
cp ../2KY10_built.pdb input/
cp ../hmr4fs_eq100ps.coor input/
```

### 5.1 单副本 GBIS 诊断 (可选)
```bash
namd3 +p16 gbis_netlrts_single.conf > gbis_netlrts_single.log 2>&1
```
**目的**: 排查 GBIS 在 netlrts-smp 下是否崩溃

### 5.2 两轮测试
```bash
chmod +x run_tiger2_test.sh
./run_tiger2_test.sh
```
**检查**:
```bash
grep -H 'End of program' output/*/tiger2_test.*.log  # 4 个都应有
grep -H -Ei 'FATAL ERROR|calcGBIS|Segmentation' output/*/tiger2_test.*.log  # 应无输出
```

### 5.3 正式 417 cycles
```bash
chmod +x run_tiger2_100ns.sh
nohup ./run_tiger2_100ns.sh > tiger2_100ns_launcher.log 2>&1 &
echo $! > tiger2_100ns.pid
```

### 5.4 监控
```bash
# 查看进程
ps -eo pid,ppid,etime,%cpu,cmd | grep -E '[n]amd3|[c]harmrun'

# 查看步数
for f in production/*/tiger2_prod.*.log; do
  printf '%s step=' "$f"
  awk '/^ENERGY:/{s=$2} END{print s+0}' "$f"
done

# 或使用监控脚本
python3 tiger2/monitor_tiger2.py production
```

### 5.5 断点续跑
```bash
# 1. 确认 restart 文件完整 (cycle 50)
ls production/*/tiger2-prod.job0.restart50.*.{tcl,coor,vel,xsc}

# 2. 修改 tiger2_resume50.conf
set restart_name "production/%s/tiger2-prod.job0.restart50"

# 3. 启动
nohup ../NAMD_3.0.2_Linux-x86_64-netlrts-smp/charmrun \
  ../NAMD_3.0.2_Linux-x86_64-netlrts-smp/namd3 \
  ++local ++n 4 ++ppn 1 +replicas 4 tiger2_resume50.conf \
  +stdout 'production/%d/tiger2_resume50.%d.log' &
```

---

## 阶段 6: 分析

### 6.1 TIGER2 历史分析
```bash
conda activate igem2026
python3 scripts/python/analyze_history.py TIGER2_2KY10/production
# 输出: tiger2_history_analysis.png
```

### 6.2 轨迹分析
```bash
# 单条 replica
python3 scripts/python/analyze_trajectory.py \
  TIGER2_2KY10/input/2KY10_hmr.psf \
  TIGER2_2KY10/production/0/tiger2-prod.job0.0.dcd

# Baseline ensemble
python3 scripts/python/analyze_trajectory.py \
  --baseline TIGER2_2KY10/production \
  TIGER2_2KY10/input/2KY10_hmr.psf
```

### 6.3 构象聚类
```bash
python3 scripts/python/cluster_conformations.py \
  TIGER2_2KY10/input/2KY10_hmr.psf \
  TIGER2_2KY10/production/0/tiger2-prod.job0.0.dcd \
  5
# 输出: representatives/cluster_*.pdb
```

---

## 依赖关系图

```
2KY10.pdb
    │
    ▼ build_2KY10_psf.tcl
2KY10_built.psf + 2KY10_built.pdb
    │
    ▼ minimize.conf
minimize.coor
    │
    ▼ make_hmr.tcl
2KY10_hmr.psf
    │
    ├──────────────────────┐
    ▼                      ▼
hmr4fs_test.conf     tiger2_base.namd
    │                      │
    ▼                      │
hmr4fs_eq100ps.conf       │
    │                      │
    ▼                      │
hmr4fs_eq100ps.coor ──────┤
                           │
    ┌──────────────────────┘
    ▼
tiger2_2ky10.namd + tiger2_100ns.conf
    │
    ▼
production/{0,1,2,3}/
    │
    ├─→ analyze_history.py
    ├─→ analyze_trajectory.py
    └─→ cluster_conformations.py
```

---

## 快速启动命令

```bash
# 一键设置环境
source ~/.bashrc

# 完整流程
cd ~/igem-2026/MD
vmd -dispdev text -e scripts/tcl/build_2KY10_psf.tcl
namd3 +p16 scripts/namd/minimize.conf
vmd -dispdev text -e scripts/tcl/make_hmr.tcl
namd3 +p16 scripts/namd/hmr4fs_test.conf
namd3 +p16 scripts/namd/hmr4fs_eq100ps.conf
cd TIGER2_2KY10 && ./run_tiger2_test.sh && nohup ./run_tiger2_100ns.sh &
```
