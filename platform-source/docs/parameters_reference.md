# Molecular Dynamics Platform 参数速查表

## 必需文件

| 文件 | 用途 | 位置 |
|---|---|---|
| `top_all36_prot.rtf` | CHARMM 蛋白拓扑 | CHARMM_toppar/ |
| `par_all36m_prot.prm` | CHARMM36m 蛋白参数 | CHARMM_toppar/ |
| `2KY10.pdb` | 初始结构 (Chimera) | MD/ |

## 关键参数对照表

### 结构构建

| 参数 | 值 | 脚本 | 说明 |
|---|---|---|---|
| `topology` | top_all36_prot.rtf | build_2KY10_psf.tcl | 力场拓扑文件 |
| `first` | GLYP | build_2KY10_psf.tcl | N 端 patch |
| `last` | CTER | build_2KY10_psf.tcl | C 端 patch |
| `mass` | 3.024 | make_hmr.tcl | HMR 氢质量 (Da) |

### 能量最小化

| 参数 | 值 | 脚本 | 可调范围 |
|---|---|---|---|
| `temperature` | 310 K | minimize.conf | 280-350 K |
| `cutoff` | 12.0 Å | minimize.conf | 10-14 Å |
| `minimize` | 10000 | minimize.conf | 5000-50000 |
| `+p16` | 16 cores | 命令行 | 1-16 |

### GBIS 隐式溶剂

| 参数 | 值 | 脚本 | 说明 |
|---|---|---|---|
| `solventDielectric` | 78.5 | tiger2_base.namd | 水介电常数 |
| `ionConcentration` | 0.15 M | tiger2_base.namd | 盐浓度 |
| `surfaceTension` | 0.005 | tiger2_base.namd | 表面张力 |

### 动力学

| 参数 | 值 | 脚本 | 可调范围 |
|---|---|---|---|
| `timestep` | 4.0 fs | tiger2_base.namd | 2.0-4.0 (HMR 依赖) |
| `rigidBonds` | all | tiger2_base.namd | all/none/h-bonds |
| `cutoff` | 16.0 Å | tiger2_base.namd | 14-18 Å |
| `langevinDamping` | 1.0 | tiger2_base.namd | 1.0-5.0 |

### TIGER2 采样

| 参数 | 值 | 脚本 | 影响 |
|---|---|---|---|
| `num_replicas` | 4 | tiger2_100ns.conf | 需要 ≤ CPU 核心数 |
| `min_temp` | 280 K | tiger2_100ns.conf | 目标温度 |
| `max_temp` | 400 K | tiger2_100ns.conf | 高温上限 |
| `num_runs` | 417 | tiger2_100ns.conf | 总 cycle 数 |
| `steps_equil1` | 500 | tiger2_100ns.conf | 加热步数 (2 ps) |
| `steps_sample` | 12000 | tiger2_100ns.conf | 采样步数 (48 ps) |
| `steps_equil2` | 2500 | tiger2_100ns.conf | 淬火步数 (10 ps) |

## 派生计算公式

```
每 cycle 步数 = steps_equil1 + steps_sample + steps_equil2
每 cycle 时间 = 步数 × timestep

当前项目:
  15000 steps × 4 fs = 60 ps/cycle
  417 cycles × 60 ps = 25.02 ns/replica
  4 replicas × 25.02 ns = 100.08 ns aggregate

Restart 间隔 = runs_per_frame × frames_per_restart × 15000 步
当前: 5 × 5 × 15000 = 375000 步 = 25 cycles = 1.5 ns
```

## 常用修改场景

### 场景 1: 加速模拟（减少 cycle 数）
```tcl
# tiger2_100ns.conf
set num_runs 100  # 原 417
# 结果: 100 × 60 ps = 6 ns/replica
```

### 场景 2: 扩大温度范围
```tcl
# tiger2_100ns.conf
set min_temp 280
set max_temp 500  # 原 400
# 注意: 高温可能导致不稳定
```

### 场景 3: 增加 replica 数量
```tcl
# tiger2_100ns.conf
set num_replicas 8  # 原 4
# 需要修改 run 脚本的 ++n 参数
# charmrun ... ++n 8 ++ppn 1 +replicas 8
```

### 场景 4: 调整热浴强度
```namd
# tiger2_base.namd
langevinDamping  3.0  # 原 1.0, 更强耦合
```

### 场景 5: 无 HMR 的 2 fs 模拟
```namd
timestep  2.0
# 不使用 HMR PSF
# structure  2KY10_built.psf (非 hmr)
```
