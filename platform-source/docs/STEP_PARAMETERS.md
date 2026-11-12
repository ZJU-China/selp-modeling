# Molecular Dynamics Platform 各步骤：输入文件与可调参数

---

## 步骤 1: build_2KY10_psf.tcl — 结构构建

### 必需输入文件
| 文件 | 说明 | 必须预先存在 |
|---|---|---|
| `2KY10.pdb` | Chimera 初始结构 | 是 |
| `top_all36_prot.rtf` | CHARMM 蛋白拓扑 | 是 |

### 可调参数
| 参数 | 当前值 | 说明 | 修改位置 |
|---|---|---|---|
| `topology` 路径 | `/home/selp/igem-2026/CHARMM_toppar/top_all36_prot.rtf` | 力场拓扑文件路径 | `build_2KY10_psf.tcl:4` |
| `pdbalias residue HIS` | `HSD` | HIS 质子化状态 (HSD/HSE/HSP) | `build_2KY10_psf.tcl:6` |
| `first` patch | `GLYP` | N 端 patch | `build_2KY10_psf.tcl:10` |
| `last` patch | `CTER` | C 端 patch | `build_2KY10_psf.tcl:11` |

### 输出文件
| 文件 | 说明 |
|---|---|
| `2KY10_built.psf` | 完整拓扑 (9563 atoms) |
| `2KY10_built.pdb` | 匹配坐标 |

---

## 步骤 2: make_hmr.tcl — 氢质量重分配

### 必需输入文件
| 文件 | 来源 |
|---|---|
| `2KY10_built.psf` | 步骤 1 输出 |

### 可调参数
| 参数 | 当前值 | 说明 | 修改位置 |
|---|---|---|---|
| `hmassrepart mass` | `3.024` | HMR 目标氢质量 (Da) | `make_hmr.tcl:8` |
| | | 范围: 1.5–4.0 | |
| | | 越大→4fs 越稳定, 但物理意义越弱 | |

### 输出文件
| 文件 | 说明 |
|---|---|
| `2KY10_hmr.psf` | HMR 拓扑 |

---

## 步骤 3: minimize.conf — 能量最小化

### 必需输入文件
| 文件 | 说明 |
|---|---|
| `2KY10_built.psf` | 步骤 1 输出 |
| `2KY10_built.pdb` | 步骤 1 输出 |
| `par_all36m_prot.prm` | CHARMM36m 参数 |

### 可调参数
| 参数 | 当前值 | 可调范围 | 说明 | 修改位置 |
|---|---|---|---|---|
| `parameters` 路径 | `.../par_all36m_prot.prm` | — | 力场参数路径 | `minimize.conf:6` |
| `temperature` | `310` K | 280–350 | 初始温度 | `minimize.conf:11` |
| `cutoff` | `12.0` Å | 10–14 | 非键截断 | `minimize.conf:17` |
| `switchdist` | `10.0` Å | 8–12 | 切换函数起始距离 | `minimize.conf:19` |
| `pairlistdist` | `14.0` Å | 12–16 | 近邻列表距离 | `minimize.conf:20` |
| `minimize` | `10000` 步 | 5000–50000 | 最小化步数 | `minimize.conf:22` |
| `+p16` (命令行) | 16 核 | 1–16 | 并行核心数 | 启动命令 |

### 输出文件
| 文件 | 说明 |
|---|---|
| `minimize.coor` | 最小化后二进制坐标 |
| `minimize.log` | 能量日志 |

---

## 步骤 4: hmr4fs_test.conf — 4fs 稳定性测试

### 必需输入文件
| 文件 | 来源 |
|---|---|
| `2KY10_hmr.psf` | 步骤 2 输出 |
| `2KY10_built.pdb` | 步骤 1 输出 |
| `gbis_test.coor` 或 `minimize.coor` | 步骤 3 输出 |

### 可调参数
| 参数 | 当前值 | 可调范围 | 说明 | 修改位置 |
|---|---|---|---|---|
| `timestep` | `4.0` fs | 2.0–4.0 | 时间步长 (需 HMR) | `hmr4fs_test.conf:35` |
| `GBIS` | `on` | on/off | 隐式溶剂开关 | `hmr4fs_test.conf:22` |
| `solventDielectric` | `78.5` | 78.5–80 | 溶剂介电常数 | `hmr4fs_test.conf:23` |
| `ionConcentration` | `0.15` M | 0–0.2 | 盐浓度 | `hmr4fs_test.conf:24` |
| `surfaceTension` | `0.005` | 0–0.01 | 表面张力 | `hmr4fs_test.conf:28` |
| `temperature` | `280` K | 280–350 | 目标温度 | `hmr4fs_test.conf:42` |
| `langevinTemp` | `280` K | 280–350 | 热浴温度 | `hmr4fs_test.conf:47` |
| `langevinDamping` | `1.0` 1/ps | 1.0–5.0 | 热浴阻尼 | `hmr4fs_test.conf:48` |
| `cutoff` | `16.0` Å | 14–18 | 非键截断 | `hmr4fs_test.conf:32` |
| `run` | `2500` 步 | — | 2500×4fs=10 ps | `hmr4fs_test.conf:57` |

### 输出文件
| 文件 | 说明 |
|---|---|
| `hmr4fs_test.coor` | 测试后坐标 |
| `hmr4fs_test.log` | 日志 |

---

## 步骤 5: hmr4fs_eq100ps.conf — 100 ps 平衡

### 必需输入文件
| 文件 | 来源 |
|---|---|
| `2KY10_hmr.psf` | 步骤 2 输出 |
| `2KY10_built.pdb` | 步骤 1 输出 |
| `hmr4fs_test.coor` | 步骤 4 输出 |

### 可调参数
与步骤 4 基本相同，额外：
| 参数 | 当前值 | 说明 | 修改位置 |
|---|---|---|---|
| `firsttimestep` | `2500` | 接续步骤 4 的步数 | `hmr4fs_eq100ps.conf:55` |
| `run` | `22500` 步 | 22500×4fs=90 ps | `hmr4fs_eq100ps.conf:57` |
| | | 加上前 10 ps 共 100 ps | |

### 输出文件
| 文件 | 说明 |
|---|---|
| `hmr4fs_eq100ps.coor` | **TIGER2 起始坐标** |
| `hmr4fs_eq100ps.vel` | 起始速度 |
| `hmr4fs_eq100ps.xsc` | 扩展系统 |

---

## 步骤 6: tiger2_base.namd — TIGER2 共享设置

### 必需输入文件
| 文件 | 说明 |
|---|---|
| `input/2KY10_hmr.psf` | HMR 拓扑 |
| `input/2KY10_built.pdb` | 原始坐标 |
| `par_all36m_prot.prm` | 力场参数 |

### 可调参数
| 参数 | 当前值 | 可调范围 | 说明 | 修改位置 |
|---|---|---|---|---|
| `timestep` | `4.0` fs | 2.0–4.0 | 时间步长 | `tiger2_base.namd:19` |
| `rigidBonds` | `all` | all/none | 约束模式 | `tiger2_base.namd:20` |
| `rigidTolerance` | `1.0e-8` | — | 约束容差 | `tiger2_base.namd:21` |
| `cutoff` | `16.0` Å | 14–18 | 非键截断 | `tiger2_base.namd:13` |
| `switchdist` | `15.0` Å | — | 切换距离 | `tiger2_base.namd:12` |
| `pairlistdist` | `18.0` Å | — | 近邻列表 | `tiger2_base.namd:14` |
| `GBIS` | `on` | on/off | 隐式溶剂 | `tiger2_base.namd:28` |
| `solventDielectric` | `78.5` | — | 溶剂介电 | `tiger2_base.namd:29` |
| `ionConcentration` | `0.15` M | — | 盐浓度 | `tiger2_base.namd:30` |
| `surfaceTension` | `0.005` | — | 表面张力 | `tiger2_base.namd:33` |
| `langevinDamping` | `1.0` 1/ps | 1.0–5.0 | 热浴阻尼 | `tiger2_base.namd:25` |

**注意**: 不要在此文件中设置 `temperature`、`langevinTemp`、`outputName`、`run` — 这些由 `tiger2_2ky10.namd` 动态控制。

---

## 步骤 7: tiger2_100ns.conf — TIGER2 正式参数

### 必需输入文件
| 文件 | 说明 |
|---|---|
| `tiger2_base.namd` | 物理设置 |
| `tiger2_2ky10.namd` | 算法主脚本 |
| `input/hmr4fs_eq100ps.coor` | 起始坐标 |

### 可调参数
| 参数 | 当前值 | 可调范围 | 说明 | 影响 |
|---|---|---|---|---|
| `num_replicas` | `4` | 2–16 | Replica 数量 | 需 ≤ CPU 核心数 |
| `min_temp` | `280` K | 280–350 | 目标温度 | 分析基准 |
| `max_temp` | `400` K | 350–600 | 高温上限 | 越高越易跨能垒 |
| `steps_equil1` | `500` | 200–1000 | 加热步数 | 2 ps × 4fs |
| `steps_sample` | `12000` | 5000–50000 | 采样步数 | 48 ps × 4fs |
| `steps_equil2` | `2500` | 1000–5000 | 淬火步数 | 10 ps × 4fs |
| `num_runs` | `417` | 1–1000 | 总 cycle 数 | 总时间 |
| `runs_per_frame` | `5` | 1–10 | DCD 帧频率 | 输出大小 |
| `frames_per_restart` | `5` | 1–10 | Restart 间隔 | 每 25 cycle 存档 |
| `output_root` | `production/%s/tiger2-prod` | — | 输出路径 | — |

### 派生公式
```
每 cycle 步数 = 500 + 12000 + 2500 = 15000
每 cycle 时间 = 15000 × 4 fs = 60 ps
每 replica 时间 = 417 × 60 ps = 25.02 ns
总 aggregate = 25.02 × 4 = 100.08 ns
Restart 间隔 = 5 × 5 = 25 cycles = 375000 步
```

### 输出文件
| 文件 | 说明 |
|---|---|
| `production/{0,1,2,3}/tiger2-prod.job0.*.dcd` | 轨迹 |
| `production/{0,1,2,3}/tiger2-prod.job0.*.history` | 温度交换记录 |
| `production/{0,1,2,3}/tiger2-prod.job0.restart*.tcl` | Restart 状态 |
| `production/{0,1,2,3}/tiger2-prod.job0.restart*.{coor,vel,xsc}` | Restart 坐标 |

---

## 步骤 8: tiger2_resume50.conf — 断点续跑

### 必需输入文件
| 文件 | 说明 |
|---|---|
| `production/{0,1,2,3}/tiger2-prod.job0.restart50.*.tcl` | Restart 状态 |
| `production/{0,1,2,3}/tiger2-prod.job0.restart50.*.coor` | Restart 坐标 |
| `production/{0,1,2,3}/tiger2-prod.job0.restart50.*.vel` | Restart 速度 |
| `production/{0,1,2,3}/tiger2-prod.job0.restart50.*.xsc` | Restart 系统 |

### 可调参数
| 参数 | 当前值 | 说明 | 修改位置 |
|---|---|---|---|
| `restart_name` | `production/%s/tiger2-prod.job0.restart50` | Restart 文件路径模式 | `tiger2_resume50.conf:1` |
| | | 修改数字 50 为其他 cycle 编号 | |

### 注意事项
- 四条 replica 的 restart 文件必须**成套存在**
- 不要混用不同 cycle 的 restart
- 续跑后新数据写入 `job1`，旧数据保留为 `job0`

---

## 步骤 9: Python 分析脚本

### analyze_history.py
| 参数 | 默认值 | 说明 |
|---|---|---|
| `production_dir` | 命令行传入 | production 目录路径 |
| `num_replicas` | 4 | Replica 数量 |

### analyze_trajectory.py
| 参数 | 默认值 | 说明 |
|---|---|---|
| `psf_file` | 命令行传入 | PSF 文件 |
| `dcd_file` | 命令行传入 | DCD 轨迹 |
| `max_frames` | None | 最大帧数限制 |
| `output_prefix` | `traj_analysis` | 输出前缀 |

### cluster_conformations.py
| 参数 | 默认值 | 说明 |
|---|---|---|
| `psf_file` | 命令行传入 | PSF 文件 |
| `dcd_file` | 命令行传入 | DCD 轨迹 |
| `n_clusters` | 5 | 聚类数 |
| `method` | `medoid` | 代表构象选择方法 |

### monitor_tiger2.py
| 参数 | 默认值 | 说明 |
|---|---|---|
| `production_dir` | 命令行传入 | production 目录 |
| `num_replicas` | 4 | Replica 数量 |
| `target_cycles` | 417 | 目标 cycle 数 |
