# 模拟方法学原理：TIGER2 与 GROMACS CG

> 本文从平台当前实际任务配置出发，说明两类模拟的算法原理、本项目的具体参数选择及其对合成生物学研究的意义。

## 适用范围

| 任务 | 原理覆盖 |
|---|---|
| `tiger2_legacy` / `tiger2_2ky5` / `tiger2_gpu` / `tiger2_zju`（NAMD, TIGER2-REMD） | 第一章 |
| `gromacs_cg_zju`（Martini 3.0.0 周期交联网络，成对盒剪切） | 第二章 |
| `CG/CG_platform_handoff_20260907` 交接包（32 链理论分析 + GROMACS 输入准备） | 第二章 |

---

## 一、TIGER2 原理

### 1. 算法身份

TIGER2 是 Brown & Walsh (2014, *Comp. Phys. Comm.*) 的温度副本交换（T-REMD）变体，主脚本 `tiger2_2ky10.namd` 头注明确要求引用该文献。别名"Temperature-Interpolated Global Replica-Exchange"。

### 2. 与经典 REMD 的关键区别

经典 REMD：所有副本长期在各自温度下并行演化、相邻温度间实时交换，需要足够副本数以保证温度分布重叠，开销大。

TIGER2：**只有基线温度是"真"物理态**，其余温度只作短暂"加热采样"。每个 cycle 分三段：

```text
equil1 (500 步 @T_sample)
    → sample (12000 步 @T_sample)
    → 速度缩放回基线 (rescalevels)
    → equil2 (2500 步 @T_base)
    → Metropolis 交换 → 全局重新排序
```

- `rescalevels sqrt(1.0*min_temp/replica(temperature))`：采样结束时把速度整体缩放到基线温度对应的能量，再在基线做 10 ps 平衡后再交换。
- 交换在**同一基线温度**进行，Metropolis 判据只依赖势能差：

```text
Δ = (1/T1 − 1/T2)/kB × (U2 − U1)     # kB = 0.001987191 (脚本中 BOLTZMAN)
接受 iff Δ<0 或 exp(−Δ) > rand()
```

- **全局排序**：基线副本随机挑选一个对手做 Metropolis 交换，之后其余副本按势能 `lsort` 排序，重新分配到空温度位，最大化混合效率（对应 `rselect` / `replicaRecv` 逻辑）。

### 3. 本项目实际参数

来源于 `tiger2_100ns.conf` / `tiger2_2ky10.namd`，与 `docs/STEP_PARAMETERS.md`、`docs/tiger2-guide.md` 一致：

| 项 | 值 | 说明 |
|---|---|---|
| 副本数 | 4 | 需 ≤ CPU 核数 |
| 温度梯度 | 280 / 320 / 360 / 400 K | 几何插值 `T_i = T_min·(T_max/T_min)^{i/(N-1)}` |
| 每 cycle | 500 + 12000 + 2500 = 15000 步 | = 60 ps @4fs |
| legacy/GPU 总 cycle | 417 | 25.02 ns/副本，aggregate 100.08 ns |
| 2KY5 总 cycle | 1667 | 100 ns/副本 |
| 力场/溶剂 | CHARMM36m + GBIS 隐式溶剂 | ε=78.5，离子 0.15 M，表面张力 0.005 |
| 时间步 | 4 fs | 依赖 HMR（氢质量 3.024）+ `rigidBonds all` |
| 控温 | Langevin 阻尼 1/ps；`langevinPiston` 同步 | — |
| 截断 | cutoff 16 Å / switch 15 Å / pairlist 18 Å | — |

### 4. 为什么对 SELP 有意义

- 2KY10 是 750 aa 弹力蛋白样（SELP）重复性体系：构象能垒众多、模式重复，而显式溶剂盒巨大、采样昂贵。
- GBIS 隐式溶剂 + 4 副本使 CPU 上即可完成 100 ns aggregate 采样，已 100% 完成（`tiger2_legacy`）。
- TIGER2 用"短暂高温 + 基线交换"而非多副本低温长平衡，让高能态构象在基线温度以正确 Boltzmann 权重被保留。`tiger2_legacy` 的簇分析结果（Semi-compact 68.1% / Extended 31.9%，k=2, silhouette 0.64）即由该机制采样所得。

---

## 二、GROMACS CG 模拟原理

构建两级：**Martini 3 粗粒化映射** 与 **周期交联网络的力学测量**。

### 1. 粗粒化映射

| 项 | 值 |
|---|---|
| 映射规则 | 约 4 个重原子 → 1 个 CG 珠子 |
| 单链 | 564 aa → 964 CG 珠子（每残基 1 BB + 侧链 SC） |
| 交联位点 | 每链 14 个 Tyr，其中 10 个核心 Tyr 参与建网（`CORE_TYR_SITES`） |
| 化学本质 | 酪氨酸侧链 SC1 的二酪氨酸交联（氧化偶联成 dityrosine），把蛋白链焊成水凝胶网络 |

32 链 × 964 beads = 30,848 beads，正交盒 335.788 × 312.742 × 241.690 Å（交接包 network_20）；8 链体系（ZJU 生产）盒约 20×19×15 nm。

### 2. 周期交联网络生成（拓扑 QC gate）

- `generator.py` 用周期图（`PeriodicNetwork`）建模：`Edge(chain_a, chain_b, shift_x/y/z, site_a, site_b)`，链可跨 PBC 盒界连接。
- 网络必须满足：单一连通分量、最小度 ≥2（无悬垂末端）、**周期秩 3**（x/y/z 三个方向均贯通），才是宏观水凝胶的拓扑必要条件。
- 交联以拓扑谐振键写入 GROMACS，`funct 6, b0 = 0.350 nm`，**三级强力常数**：

```text
soft:   kb = 100  kJ·mol⁻¹·nm⁻²
medium: kb = 1000 kJ·mol⁻¹·nm⁻²
final:  kb = 4000 kJ·mol⁻¹·nm⁻²
```

> **为什么三级阶梯**：刚性嵌入后的 coordinates 存在大量 <1.8 Å 链间近接触（network_20 为 287 对），直接上最终 kb 会产生爆炸性排斥力。soft 阶段用极软键先把几何弛豫打开，逐级收紧。交接包规定：soft 未通过 QC 不得自动进入 medium/final（gate 规则）。

### 3. 力学测量方法学

#### 3.1 成对盒剪切（positive control，ZJU 实测）

对同一网络施加 ±γ 的盒形变（γ=0.10/0.20），固定形变盒跑 10 ns NVT（310 K, v-rescale, dt 20 fs，无 barostat），从压力张量提取剪切模量：

```text
G(t) = [σ(+γ,t) − σ(−γ,t)] / (2γ)
```

偶函数应力（张力基线）在差式中自动抵消，只剩纯剪切响应。报告分平面（xy/xz/yz）× 幅值，并分级标注"单网络 = technical-only；≥3 网络才有网络层置信区间"。

#### 3.2 无热剪切诊断（AQS）

不跑 MD：固定盒形和体积做能量最小化，取偶势能曲率为 `G_energy`、奇剪切应力斜率为 `G_stress`。用于快速筛选——positive33 网络 `G_crosslink` 各面均为正（23–120 kPa），证明"交联密度↑ → 剪切模量响应↑"可在模型内被检测（ordinary 网络为负/杂乱对照）。

#### 3.3 理论区间（rubber.py）

用网图做 **Scanlan–Case 约简**求得有效交联点/有效超链，给出 phantom（=2.22 kPa）到 affine（=10.37 kPa）的工作区间；不可压缩近似 E≈3G 得杨氏模量 6.7–15.6 kPa。三轴等体积小应变扫描得 x/y/z 模量 6.07 / 6.79 / 7.14–16.66 kPa，各向异性比 1.176（20 候选 1.261 ± 0.152）。

### 4. GROMACS 计算参数（ZJU 实测）

| 阶段 | 设置 |
|---|---|
| EM | steep + Verlet，Reaction-Field（ε=15, ε_rf=0），rlist/rcoulomb/rvdw=1.1 nm，`emtol=100`，50000 步 |
| NVT/NPT | `dt=0.020 ps`；NVT 100 ps + 1 ns → NPT 5 ns @310 K，v-rescale（τ=1 ps）+ c-rescale 各向同性（τ=4 ps, ref_p=1 bar），`gen_vel=yes` |
| 剪切 | mdp 中无 `deform`（盒形变在 setup 阶段静态写好），固定盒 NVT 500000 步 = 10 ns |
| 力场 | Martini 3.0.0（`martini_v3.0.0.itp` + 964-bead `molecule_0.itp`，受控输入文件） |

---

## 三、对合成生物学研究意义

1. **跨尺度衔接**：TIGER2 在分子层面回答"SELP 在温度下如何折叠/两态占比"（统计力学系综）；GROMACS CG 在材料层面回答"交联网络多硬、哪个方向硬"（网络拓扑力学 + 连续介质近似）。二者由 AA→CG 映射衔接，构成从序列 → 构象 → 宏观材料性能的完整设计回路。

2. **先验证测量方法，再产生真实数据**：CG 的成对盒剪切、AQS 诊断与理论 rubber 区间互为校验。positive33 对照组证明"交联多 → 模量高"的物理规律在 Martini 模型中可被正确检测，为后续 32 链真实网络力学测量背书——这是合成生物学"方法先于数据"的可信性要求。

3. **交联位点 = 序列编码的可编程设计变量**：二酪氨酸交联由序列中 Tyr 的位置决定。周期网络生成 + 拓扑 QC gate 让"Tyr 放哪里才能得到连通、无悬臂、模量可预测的水凝胶"成为可在电脑上先于实验回答的问题，是蛋白质材料理性设计（sequence → topology → property）的量化工具。

4. **TIGER2 提供构象统计基线**：Semi-compact / Extended 两态占比是可发表、可证伪的定量假说，服务于弹性蛋白（SELP）温度响应与机械功能的构象解释。

5. **可审计性**：每一步保存独立 run 与输入/参数/输出/log/gate 决定；结果 JSON 带置信区间与"解释层级"标注（区分技术小试 vs 网络结论），符合 iGEM 对数据可追溯、结论有置信标注的要求。

---

## 相关文档

- `docs/STEP_PARAMETERS.md` — 各阶段具体数值表与可调范围
- `docs/tiger2-guide.md` — TIGER2 启动/重启操作指南
- `docs/full-workflow-guide.md` / `WORKFLOW.md` — 端到端管线步骤
- `docs/parameters_reference.md` — 力场/结构构建参数速查