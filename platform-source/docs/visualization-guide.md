# Molecular Dynamics Platform Visualization Guide

> 适用项目：2KY10，750 aa SELP 体系  
> 模拟方法：CHARMM36m + GBIS + HMR（4 fs）+ TIGER2  
> 正式采样：4 replicas，280–400 K，417 cycles  
> 配套文档：[full-workflow-guide.md](full-workflow-guide.md)

## 1. 可视化的目的

本阶段的可视化不只是“把蛋白画出来”，而是要回答三类问题：

1. **模拟是否正常运行？**
   四条 replicas 是否同步、温度和能量是否稳定、断点续跑是否连续。
2. **TIGER2 是否产生了有效增强采样？**
   replicas 是否在温度层级之间移动、是否发生有效交换、淬火是否充分。
3. **蛋白质得到了什么构象系综？**
   长链是否塌缩、哪些区域柔性较高、有哪些主要构象簇、哪些结构适合进入粗粒化模拟。

可视化流程：

```text
运行状态检查
  -> 原始 replica 轨迹预览
  -> 温度轨迹和交换行为
  -> 势能与淬火检查
  -> 根据 history 拆分 280 K baseline ensemble
  -> Rg、端到端距离、RMSD/RMSF、二级结构、接触图
  -> 收敛检查
  -> 构象聚类
  -> 导出代表结构
  -> 粗粒化模拟
```

## 2. 当前模拟的时间和轨迹关系

当前每个 TIGER2 cycle 包含：

```text
500 steps heating/equilibration = 2 ps
12000 steps sampling           = 48 ps
2500 steps quenching           = 10 ps
总计 15000 steps               = 60 ps/replica
```

正式模拟：

```text
417 cycles × 60 ps = 25.02 ns/replica
4 replicas × 25.02 ns = 100.08 ns aggregate
目标步数 = 417 × 15000 = 6,255,000 steps/replica
```

这里的 100.08 ns 是四条 replicas 的 aggregate 时间，不是 100 ns 的纯 280 K 常规 MD。

当前 TIGER2 脚本通常每个 cycle 写一帧 DCD，因此每条 replica 完整运行大约产生 417 帧。断电续跑后帧可能分布在 `job0` 和 `job1` 中。

## 3. 模拟运行时就能做的可视化

### 3.1 进度和四条 replicas 同步情况

先检查进程：

```bash
ps -eo pid,ppid,etime,%cpu,%mem,cmd | grep -E '[n]amd3|[c]harmrun'
```

正常情况应看到：

- 1 个 `charmrun`。
- 4 个 `namd3`。
- 每个 `namd3` 约占用一个 CPU 核心。

查看四个最新步数：

```bash
cd ~/igem-2026/MD/TIGER2_2KY10

for f in production/*/tiger2_resume50.*.log; do
  printf '%s latest_step=' "$f"
  awk '/^ENERGY:/{s=$2} END{print s+0}' "$f"
done
```

把 replica 0 的步数换算成时间和百分比：

```bash
s=$(awk '/^ENERGY:/{s=$2} END{print s+0}' \
production/0/tiger2_resume50.0.log)

awk -v s="$s" 'BEGIN {
  printf "Latest step: %d / 6255000\n", s
  printf "Completed cycles: %.1f / 417\n", s/15000
  printf "Per replica: %.3f ns\n", s*0.000004
  printf "Four-replica aggregate: %.3f ns\n", s*0.000016
  printf "Progress: %.2f%%\n", 100*s/6255000
}'
```

建议最终画一张进度图：

| 图形元素 | 内容 |
|---|---|
| X 轴 | 实际日期时间或 cycle |
| Y 轴 | 完成百分比或最新 step |
| 曲线 | 四条 replicas |
| 标记线 | cycle 50 断电/续跑位置 |

四条曲线应基本重合。TIGER2 会在 barrier 同步，因此短时间略有差异正常；长期差距很大则需要检查。

### 3.2 温度随时间变化

TIGER2 的四个温度大致为：

```text
280 K, 315 K, 355 K, 400 K
```

建议画：

- X 轴：cycle。
- Y 轴：温度或温度层级。
- 每条线：一个 walker/replica。

理想情况：

- 每条 replica 都能访问多个温度。
- 不应有 replica 长期困在一个温度。
- cycle 50 前后的温度轨迹能够正确衔接。

重要：目录编号不是固定温度。`production/0` 并不永远等于 280 K，因为 replicas 会交换温度位置。温度轨迹必须结合 `.history` 文件分析。

### 3.3 温度访问次数和交换矩阵

推荐制作两类图。

#### 温度访问柱状图

```text
X 轴：280、315、355、400 K
Y 轴：访问次数
颜色：replica 0–3
```

它可以判断每个 walker 是否真正遍历了温度空间。

#### 交换矩阵热图

```text
X/Y 轴：温度层级或 replica 编号
颜色：交换次数或交换概率
```

它可以显示哪些温度区间交换顺畅，哪些区间存在采样瓶颈。

还应记录 `EX_ratio`，但不能只靠单个接受率判断采样是否充分，必须同时观察温度轨迹和访问次数。

### 3.4 势能和淬火过程

每轮的 2500-step quenching 负责把所有 replicas 拉回 baseline 温度。建议画：

```text
X 轴：step 或 cycle 内相对时间
Y 轴：potential energy
曲线：四条 replicas
```

重点检查每轮末尾：

- 实际温度是否回到约 280 K。
- 四条 replicas 的势能范围是否开始相互交叉。
- 是否出现突然的大幅能量跳变。
- 是否出现 `nan`、`moving too fast` 或约束失败。

如果淬火阶段结束时各 replicas 的能量仍明显分离，说明 2500 steps 可能不足，需要重新评估 quenching 长度。

## 4. VMD 中预览原始轨迹

### 4.1 加载顺序

先加载 PSF，再把 DCD 加到同一个 molecule：

```tcl
mol new input/2KY10_hmr.psf type psf waitfor all
mol addfile production/0/tiger2-prod.job0.0.dcd type dcd waitfor all
```

续跑后还可能存在：

```text
production/0/tiger2-prod.job1.0.dcd
```

不要在尚未检查重复区间前，直接把 job0 和 job1 全部拼在一起。

### 4.2 推荐显示方式

整体构象：

```text
Selection: all
Drawing Method: NewCartoon
Coloring Method: ResID 或 Secondary Structure
```

重点残基：

```text
Selection: resname TYR
Drawing Method: Licorice
Coloring Method: Name
```

末端：

```text
N 端 selection: resid 1
C 端 selection: resid 750
Drawing Method: VDW
```

推荐设置：

- 白色背景。
- Orthographic projection。
- N 端和 C 端使用固定的不同颜色。
- 两端结构域和中间 SELP 重复区域使用不同颜色。
- 制作对比图时保持相同缩放比例和观察方向。

### 4.3 原始轨迹预览检查什么

- 是否有断链。
- 是否有原子或片段突然飞走。
- 是否发生不合理的瞬间塌缩。
- 完全伸展长链是否逐渐弯曲或形成紧凑结构。
- 两端结构域是否保持基本完整。
- 续跑前后是否发生坐标跳变。

原始 replica 轨迹混合了不同温度，只适合做运行质量检查，不能直接作为 280 K 结构演化来解释。

## 5. 构建 280 K baseline ensemble

这是正式结构分析前最重要的一步。

### 5.1 为什么需要拆分

TIGER2 中 replicas 会交换温度位置，因此：

```text
replica 文件编号 != 永久固定温度
```

必须读取每条 `.history`，确定每个 cycle 哪个 DCD 帧位于 baseline，然后把这些帧按时间顺序重新组合。

`.history` 通常记录：

```text
step  replica_location  assigned_temperature  actual_temperature  potential
```

分析应依据温度位置或 baseline 标识，而不是仅依据目录编号。

### 5.2 断点续跑的重复区间

当前从 cycle 50 checkpoint 续跑：

```text
cycle 50 = 750000 steps
```

正式分析时：

1. `job0` 只保留到 cycle 50 的有效分支。
2. `job1` 从 cycle 50 之后接续。
3. 如果断电前 job0 已经写出 cycle 50 后的部分帧，这些帧不能与 job1 重复统计。
4. 结合 `.history`、DCD 帧数和 restart step 检查连续性。

### 5.3 baseline ensemble 通过条件

- 每个 cycle 最多贡献一个 baseline 构象。
- step/cycle 顺序严格递增。
- cycle 50 附近没有重复帧或时间倒退。
- baseline 实际温度接近 280 K。
- PSF、DCD 和 history 的帧数关系能够对应。

## 6. 蛋白质结构指标

### 6.1 回转半径 Rg

Rg 描述蛋白质整体尺寸，对 750 aa 柔性长链比全链 RMSD 更容易解释。

建议画两张图。

#### Rg 时间序列

```text
X 轴：baseline cycle 或模拟时间
Y 轴：Rg，Å
```

可以判断：

- 完全伸展结构是否逐渐塌缩。
- 蛋白尺寸是否进入相对稳定范围。
- 后期是否仍持续单向变化。

#### Rg 分布

对去除未平衡区间后的 baseline 帧绘制直方图或密度图。多个峰可能代表伸展态、中间态和紧凑态等多个构象群体。

分析时需固定原子选择，例如始终使用所有重原子或所有 CA，不能不同图混用不同选择。

### 6.2 N 端到 C 端距离

建议使用第一个和最后一个 CA 原子之间的距离：

```text
X 轴：baseline cycle
Y 轴：end-to-end distance，Å
```

Rg 与端到端距离的联合解释：

| Rg | 端到端距离 | 可能构象 |
|---|---|---|
| 大 | 大 | 整体伸展 |
| 较大 | 小 | 弯曲、回折或近环状 |
| 同时下降 | 同时下降 | 整体塌缩 |
| 稳定 | 大幅波动 | 整体尺寸稳定但末端灵活 |

还应画 `Rg vs end-to-end distance` 二维散点图。不同构象状态通常形成不同点云区域。

### 6.3 RMSD

建议分别计算：

- 全链 CA RMSD。
- N 端结构域 RMSD。
- C 端结构域 RMSD。
- 中间 SELP 重复区域 RMSD。

长而柔性的 SELP 全链 RMSD 很容易很大，因此不能简单地把“RMSD 小”当作唯一稳定标准。RMSD 更适合检查持续漂移、比较结构域稳定性和构象聚类。

### 6.4 RMSF

```text
X 轴：residue ID 1–750
Y 轴：RMSF，Å
```

它可以显示：

- 哪些结构域比较稳定。
- 哪些 linker 或重复序列更柔性。
- 两端结构域与中间 SELP 区域的波动差异。

计算 RMSF 前需要先对一个相对稳定的参考区域进行结构对齐，否则整体平移和旋转会污染残基波动。

### 6.5 二级结构时间图

可以使用 VMD Timeline、STRIDE 或 DSSP。

推荐热图：

```text
X 轴：baseline cycle
Y 轴：residue ID
颜色：coil、turn、helix、beta-sheet
```

重点观察：

- 丝素样 `GAGAGS` 区域是否形成局部 beta-sheet。
- 弹性蛋白样 `GVGVP` 区域是否保持较高柔性。
- 两端结构域是否在高温采样中发生明显破坏。
- 新形成的二级结构是否持续存在，还是短暂波动。

### 6.6 残基接触图

可以把两个残基的任意重原子距离小于约 4.5–6 Å 定义为接触。

接触概率热图：

```text
X/Y 轴：residue ID
颜色：baseline ensemble 中的接触概率
```

可以观察：

- 哪些远程区段发生稳定接触。
- 重复单元之间是否存在偏好相互作用。
- 两端结构域是否与中间 SELP 区域结合。
- Tyr–Tyr、盐桥或其他关注残基的接触概率。

接触阈值和原子选择必须在方法中明确报告。

### 6.7 SASA

虽然使用 GBIS 而不是显式水，仍可根据结构几何计算 solvent-accessible surface area。

建议分析：

- 总 SASA。
- 疏水残基 SASA。
- Tyr 残基 SASA。

如果 Rg、端到端距离和 SASA 同时下降，通常表示整体塌缩；如果 Rg 下降但 SASA 变化不明显，可能主要是长链弯曲。

## 7. 收敛与平衡判断

不能因为模拟达到目标步数就自动认为已经收敛。

建议把 baseline ensemble 分成几个时间块，例如：

```text
前 25%
中间 25%
后 25%
最后 25%
```

比较每个块的：

- Rg 分布。
- 端到端距离分布。
- 势能分布。
- 二级结构比例。
- 主要构象簇占比。

较理想的表现：后两个时间块的分布大致重合，没有明显持续漂移。

当前 100.08 ns 是较短的 aggregate 采样。即使后期指标趋稳，也应表述为“在当前有限采样范围内趋于稳定”，不能宣称完全覆盖全部构象空间。

## 8. 构象聚类

### 8.1 聚类输入

只使用：

- 正确拆分后的 baseline ensemble。
- 已删除未平衡区间的帧。
- 已处理 cycle 50 断点重复区间的连续轨迹。

### 8.2 聚类特征

可选方法：

- 全链或指定区域的 CA RMSD。
- 基于接触图的距离。
- Rg、端到端距离等低维结构指标。
- PCA/TICA 后的低维坐标。

参考文献使用 K-means，并采用约 6 Å RMSD 进行结构集合划分。对于当前 750 aa 柔性长链，需要验证 6 Å 是否会把绝大多数帧都分成单独小簇；必要时应针对结构域和 SELP 区域分别聚类。

### 8.3 聚类结果可视化

建议展示：

1. 前 3–5 个构象簇的占比柱状图。
2. 每个主要簇的中心结构。
3. 各簇在 `Rg–end-to-end` 二维空间中的位置。
4. 每个簇随 cycle 的出现时间。
5. 各簇的平均接触图或二级结构比例。

代表结构应选择簇中心或距离中心最近的真实轨迹帧，而不是任意最后一帧。

## 9. 推荐的论文/报告图表

### 第一组：模拟是否可信

1. 四条 replicas 的 step/cycle 进度图。
2. 四条 walkers 的温度轨迹图。
3. 温度访问次数柱状图或交换矩阵。
4. 典型 cycle 的温度和势能淬火曲线。

### 第二组：蛋白发生了什么变化

5. baseline Rg 时间序列和分布。
6. baseline end-to-end distance 时间序列。
7. `Rg–end-to-end` 二维散点或自由能样式分布图。
8. RMSF 或二级结构时间热图。
9. 残基接触概率图。

### 第三组：最终代表构象

10. 主要构象簇占比。
11. 前 3–5 个簇中心结构的统一视角对比。
12. 初始完全伸展结构、最小化结构和代表结构对比。

如果版面有限，至少保留：

```text
温度轨迹
交换/访问统计
Rg
端到端距离
二级结构或接触图
聚类中心结构
```

## 10. 当前阶段的执行顺序

### 模拟仍在运行时

- [ ] 定期记录 step、cycle、百分比和运行时间。
- [ ] 确认 1 个 charmrun + 4 个 namd3。
- [ ] 确认四条 replicas 的最新 step 同步增长。
- [ ] 记录温度、势能和异常日志。
- [ ] 预览原始 DCD，检查断链和坐标跳变。

### 模拟结束后

- [ ] 检查四条 replicas 都正常 `End of program`。
- [ ] 检查所有 DCD、history 和 restart 文件。
- [ ] 处理 job0/job1 和 cycle 50 重复区间。
- [ ] 根据 history 拆分 280 K baseline ensemble。
- [ ] 计算 Rg、端到端距离、RMSD/RMSF、二级结构和接触图。
- [ ] 进行分块收敛检查。
- [ ] 删除未平衡区间后聚类。
- [ ] 导出多个代表全原子结构。
- [ ] 记录代表结构的 Rg、端到端距离和簇占比。
- [ ] 准备进入 Martini/GROMACS 粗粒化。

## 11. 结果解释的注意事项

1. 原始 replica 目录不能直接当作固定温度轨迹。
2. 不能把四条高低温混合轨迹直接拼成 280 K ensemble。
3. 不能只用最后一帧代表整个柔性蛋白构象。
4. 不能只靠 VMD 截图判断是否平衡。
5. 全链 RMSD 很大不一定表示模拟失败。
6. 聚类前必须处理断点续跑的重复区间。
7. 图中必须注明使用的是 raw replica、baseline ensemble 还是所有温度的 aggregate 数据。
8. 报告中必须注明 100.08 ns 是四条 replicas 的 aggregate 时间。
9. 当前采样时间有限，代表结构应被描述为候选构象，而不是唯一平衡结构。

## 12. 最终交付文件建议

```text
visualization/
├── progress.csv
├── progress.png
├── temperature_trace.csv
├── temperature_trace.png
├── temperature_visits.png
├── exchange_matrix.png
├── energy_quench.png
├── baseline_280K.dcd
├── baseline_280K_history.csv
├── rg.csv
├── rg_trace.png
├── rg_distribution.png
├── end_to_end.csv
├── end_to_end_trace.png
├── rg_vs_end_to_end.png
├── rmsf.png
├── secondary_structure.png
├── contact_probability.png
├── cluster_population.png
├── cluster_01_center.pdb
├── cluster_02_center.pdb
├── cluster_03_center.pdb
└── analysis_notes.md
```

所有图表应保存对应 CSV 或原始数据，保证后续能够重新绘图和复核。
