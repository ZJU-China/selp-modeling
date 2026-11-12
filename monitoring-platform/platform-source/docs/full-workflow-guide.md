# Molecular Dynamics Platform Workflow Guide：从 PDB 到 GBIS/HMR/TIGER2 采样

> 适用项目：2KY10，750 aa SELP 蛋白体系  
> 软件组合：VMD/psfgen + NAMD 3.0.2 + CHARMM36m + GBIS + HMR + TIGER2  
> 当前服务器工作根目录：`/home/selp/igem-2026/MD`  
> 文档日期：2026-07-15

## 目录

1. Molecular Dynamics Platform 的含义和工作流
2. 本项目的关键数字
3. 软件、安装包和输入文件
4. VMD/NAMD 环境配置
5. PDB 与 PSF 构建
6. CHARMM36m + GBIS 最小化
7. HMR 与 4 fs 验证
8. TIGER2 原理
9. TIGER2 配置文件关系
10. 测试和正式运行
11. 实时进度监控
12. 断电后的断点续跑
13. 结果检查与可视化
14. 粗粒化模拟交接
15. 常见错误处理
16. 分阶段检查清单
17. 复现实验归档
18. 当前项目状态

## 1. Molecular Dynamics Platform 在本项目中指什么

Molecular Dynamics Platform 在这里指 fully atomistic molecular dynamics，即全原子分子动力学。蛋白质中的每个原子（包括氢原子）都被显式表示；水没有逐个显式建模，而是由 NAMD 的 GBIS 连续介质隐式溶剂近似。

本项目的主要目标不是从一条完全伸展的链直接得到唯一“最终结构”，而是：

1. 建立与 CHARMM36m 一致的全原子拓扑和坐标。
2. 消除初始结构中的原子碰撞。
3. 在 GBIS 中完成短程稳定性验证。
4. 通过 HMR 将稳定时间步长从 2 fs 提高到 4 fs。
5. 使用 TIGER2 在多个温度间增强构象采样。
6. 从平衡后的 baseline ensemble 中聚类并筛选代表构象。
7. 将代表构象交给后续粗粒化模拟，而不是只使用任意最后一帧。

整体流程：

```text
氨基酸序列
  -> Chimera 构建完全伸展 PDB
  -> 检查 PDB 坐标、残基数和重复坐标
  -> VMD/psfgen + CHARMM36 topology 生成 PSF/PDB
  -> 检查 PSF/PDB 原子数和顺序
  -> CHARMM36m + GBIS 能量最小化
  -> 生成 HMR PSF（氢质量 3.024 Da）
  -> 4 fs 短测试
  -> 280 K、100 ps 平衡
  -> 单副本 GBIS/netlrts-smp 诊断
  -> 4 replicas、2 cycles TIGER2 测试
  -> 417 cycles 正式 TIGER2
  -> 断点续跑与完整性检查
  -> baseline 轨迹拆分、结构指标和聚类
  -> 输出全原子代表构象
  -> Martini/GROMACS 粗粒化
```

## 2. 本项目的关键数字

| 项目 | 当前设置 |
|---|---:|
| 蛋白长度 | 750 aa |
| psfgen 后总原子数 | 9563 |
| 初始非氢 PDB 原子数 | 约 4787（以实际文件为准） |
| 力场 | CHARMM36m protein |
| 溶剂 | NAMD GBIS 隐式溶剂 |
| 盐浓度 | 0.15 mol/L |
| HMR 目标氢质量 | 3.024 Da |
| 时间步长 | 4 fs（HMR 后） |
| TIGER2 replicas | 4 |
| 温度范围 | 280–400 K，指数分布 |
| 每轮加热 | 500 steps = 2 ps |
| 每轮采样 | 12000 steps = 48 ps |
| 每轮淬火 | 2500 steps = 10 ps |
| 每个 cycle | 15000 steps = 60 ps/replica |
| 正式 cycles | 417 |
| 每条 replica 总时间 | 25.02 ns |
| 4 条 aggregate 总时间 | 100.08 ns |
| 每个 replica 目标步数 | 6,255,000 steps |

重要：这里的“100 ns”是四条 replicas 的 aggregate 时间，不是每条 replica 100 ns，也不是 100 ns 的纯 280 K 常规 MD。每条 replica 实际运行 25.02 ns。

## 3. 需要准备的软件和文件

### 3.1 软件安装包

当前项目使用：

```text
VMD 1.9.4a57, LINUXAMD64
NAMD_3.0.2_Linux-x86_64-multicore
NAMD_3.0.2_Linux-x86_64-netlrts-smp
CHARMM36/CHARMM36m toppar 文件
TIGER2 Tcl/NAMD 脚本
```

两个 NAMD 包的用途不同：

| 安装包 | 用途 |
|---|---|
| `NAMD_3.0.2_Linux-x86_64-multicore` | 单副本最小化、短程 GBIS/HMR 测试 |
| `NAMD_3.0.2_Linux-x86_64-netlrts-smp` | `charmrun +replicas` 多副本 TIGER2 |

不要在没有 AMD GPU/ROCm 环境的服务器上使用 `multicore-HIP`。出现下面错误说明 HIP 运行库不匹配，而不是 PATH 配置错误：

```text
libamdhip64.so.6: cannot open shared object file
```

服务器若没有可用 GPU，CPU 版 `multicore` 和 `netlrts-smp` 就足够完成当前流程。

### 3.2 分子和力场文件

| 文件 | 作用 | 是否必须 |
|---|---|---|
| `2KY10.pdb` | Chimera 生成的初始坐标 | 是 |
| `top_all36_prot.rtf` | CHARMM 蛋白拓扑；供 psfgen 建立原子和连接 | 是 |
| `par_all36m_prot.prm` | CHARMM36m 蛋白参数；供 NAMD 计算势能 | 是 |
| `2KY10_built.psf` | psfgen 生成的完整拓扑 | 后续必须 |
| `2KY10_built.pdb` | 与 PSF 原子顺序一致的完整坐标 | 后续必须 |
| `2KY10_hmr.psf` | HMR 后的 PSF | 4 fs 模拟必须 |
| `hmr4fs_eq100ps.coor` | 4 fs/280 K 平衡后的二进制坐标 | TIGER2 初始坐标 |
| `toppar_water_ions.str` | 显式水/离子 stream 文件 | 当前 GBIS 蛋白体系不需要 |

`RTF` 定义“有哪些原子、残基如何连接”；`PRM` 定义“这些原子类型对应什么键、角、二面角和非键参数”。二者必须来自兼容的 CHARMM 版本。

本项目的 PSF 使用 CHARMM36 蛋白拓扑生成，因此 NAMD 应使用兼容的 `par_all36m_prot.prm`。不要用 CHARMM22、AMBER 或 CGenFF 参数随意替代蛋白参数。

`toppar_water_ions.str` 中可能包含 CHARMM 命令，例如：

```text
*set nat ?NATC*
```

这类完整 stream 文件不能简单地作为 NAMD `parameters` 文件读取，否则可能出现 `UNKNOWN PARAMETER`。当前使用 GBIS，不含显式水和离子，所以不需要加载它。

### 3.3 推荐目录结构

```text
/home/selp/igem-2026/MD/
├── 2KY10.pdb
├── 2KY10_built.pdb
├── 2KY10_built.psf
├── 2KY10_hmr.psf
├── par_all36m_prot.prm
├── minimize.conf
├── hmr4fs_test.conf
├── hmr4fs_eq100ps.conf
├── hmr4fs_eq100ps.coor
├── NAMD_3.0.2_Linux-x86_64-multicore/
├── NAMD_3.0.2_Linux-x86_64-netlrts-smp/
└── TIGER2_2KY10/
    ├── input/
    │   ├── 2KY10_hmr.psf
    │   ├── 2KY10_built.pdb
    │   └── hmr4fs_eq100ps.coor
    ├── tiger2_base.namd
    ├── tiger2_2ky10.namd
    ├── tiger2_test.conf
    ├── tiger2_100ns.conf
    ├── tiger2_resume50.conf
    ├── run_tiger2_test.sh
    ├── run_tiger2_100ns.sh
    ├── run_tiger2_resume50.sh
    ├── output/{0,1,2,3}/
    └── production/{0,1,2,3}/
```

尽量使用英文目录名。NAMD/Tcl、分析脚本以及外部工具对空格、中文字符和引号的处理并不总是一致。

## 4. 安装与环境配置

### 4.1 解压前先确认文件名和当前位置

```bash
pwd
ls -lh
```

必须使用 `ls` 中真实存在的压缩包名，例如：

```bash
tar -xzf NAMD_3.0.2_Linux-x86_64-multicore.tar.gz
tar -xzf NAMD_3.0.2_Linux-x86_64-netlrts-smp.tar.gz
```

如果出现：

```text
Cannot open: No such file or directory
```

通常只是当前目录或文件名不对，不是安装包损坏。

### 4.2 VMD 环境

当前 VMD 目录：

```text
/home/selp/igem-2026/vmd-1.9.4a57
```

如果该目录中的 `bin/vmd` 可执行，可以在 `~/.bashrc` 中添加：

```bash
export VMD_HOME="$HOME/igem-2026/vmd-1.9.4a57"
export PATH="$VMD_HOME/bin:$PATH"
```

使其立即生效：

```bash
source ~/.bashrc
```

验证：

```bash
command -v vmd
vmd -dispdev text
```

出现 `vmd >` 提示符即表示文本模式正常，可输入 `quit` 退出。服务器没有图形界面或 CUDA 并不影响文本模式的 psfgen 和轨迹处理。

### 4.3 NAMD 环境

建议同时保留单副本和多副本目录：

```bash
export NAMD_MC="$HOME/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-multicore"
export NAMD_SMP="$HOME/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-netlrts-smp"
export PATH="$NAMD_MC:$PATH"
```

可将以上三行加入 `~/.bashrc`，然后：

```bash
source ~/.bashrc
```

验证单副本版本：

```bash
namd3 +p1
```

如果看到：

```text
FATAL ERROR: No simulation config file specified on command line.
```

反而说明 NAMD 可执行文件和依赖已经正常，只是尚未给 `.conf` 配置文件。

验证多副本文件：

```bash
ls -lh "$NAMD_SMP/namd3" "$NAMD_SMP/charmrun"
```

### 4.4 查看服务器 CPU

```bash
nproc
lscpu
free -h
```

当前服务器曾显示 8 physical cores、16 logical CPUs。TIGER2 当前使用 4 个 NAMD 进程，每个 replica 一个 worker；不要因为看到 16 个逻辑 CPU 就盲目启动 16 个 replicas。

## 5. 从初始 PDB 生成匹配的 PSF/PDB

### 5.1 初始结构原则

文献中的 fully extended structure 指主链处于伸展构象，不表示所有原子可以共享同一坐标，也不表示不同结构域可以彼此完全重叠。

完全伸展结构允许近似一条长链，但必须满足：

- 每个残基和原子都有有限坐标。
- 相邻残基的主链连接合理。
- 不同原子不能大量使用完全相同的 XYZ。
- 不同片段拼接后不能在空间中重叠。
- PDB 中的残基顺序必须与目标 750 aa 序列一致。

检查残基数量：

```bash
awk '/^(ATOM|HETATM)/ {print substr($0,22,5)}' 2KY10.pdb | uniq | wc -l
```

检查原子行数量：

```bash
grep -E '^(ATOM|HETATM)' 2KY10.pdb | wc -l
```

检查完全重复坐标：

```bash
awk '/^(ATOM|HETATM)/ {
  xyz=substr($0,31,24)
  n[xyz]++
}
END {
  for (xyz in n)
    if (n[xyz]>1) print "DUP:",n[xyz],xyz
}' 2KY10.pdb
```

没有输出表示不存在完全相同的 XYZ；这并不能排除距离非常近的碰撞，但能发现最严重的构建错误。

### 5.2 psf 创建脚本

创建 `build_psf.tcl`：

```tcl
package require psfgen
resetpsf

topology /home/selp/igem-2026/CHARMM_toppar/top_all36_prot.rtf

pdbalias residue HIS HSD
pdbalias atom ILE CD1 CD

segment PROT {
    pdb 2KY10.pdb
    first GLYP
    last CTER
}

coordpdb 2KY10.pdb PROT
guesscoord

writepsf 2KY10_built.psf
writepdb 2KY10_built.pdb
quit
```

关于末端 patch：`GLYP`/`CTER` 必须与实际建模意图和所用 topology 相符。如果体系需要标准带电 N 端或其他特殊末端，应根据 RTF 中可用 patch 调整，不能机械照抄。

运行：

```bash
vmd -dispdev text -e build_psf.tcl > build_psf.log 2>&1
```

检查：

```bash
grep -Ei 'error|failed to guess|unknown residue|unknown patch' build_psf.log
tail -20 build_psf.log
grep '!NATOM' 2KY10_built.psf
grep -E '^(ATOM|HETATM)' 2KY10_built.pdb | wc -l
```

本项目正确结果应为：

```text
9563 !NATOM
9563 PDB atom records
```

不要拿原始无氢 `2KY10.pdb` 配生成后的 `2KY10_built.psf` 运行 NAMD。原始 PDB 约 4787 个原子，而 PSF 是 9563 个原子，会出现：

```text
FATAL ERROR: Number of pdb and psf atoms are not the same!
```

必须使用同一次 psfgen 写出的 `2KY10_built.psf` 和 `2KY10_built.pdb`。

`failed to set coordinate for atom O/OXT` 后由 `guesscoord` 补出末端原子并不一定是致命问题，但应确认被猜测的重原子数量很少，且可视化后末端结构合理。

## 6. CHARMM36m + GBIS 能量最小化

### 6.1 原理

能量最小化不会产生具有真实时间意义的动力学轨迹。它沿势能面降低局部应力，用于消除：

- 原子过近造成的巨大排斥能。
- psfgen 猜测氢原子后的局部几何问题。
- 完全伸展模型拼接位置的键长和键角应力。

GBIS 把水视为高介电连续介质，并近似溶剂化自由能。它显著减少原子数，适合长链蛋白的快速构象筛选，但不能替代所有显式水效应。

### 6.2 最小化配置示例

`minimize.conf` 的核心可写为：

```namd
structure              2KY10_built.psf #输入蛋白结构psf
coordinates            2KY10_built.pdb #输入蛋白结构pdb

paraTypeCharmm         on
parameters             /home/selp/igem-2026/CHARMM_toppar/par_all36m_prot.prm

exclude                scaled1-4
oneFourScaling         1.0

switching              on
switchdist             15.0
cutoff                 16.0
pairlistdist           18.0

GBIS                   on
solventDielectric      78.5
ionConcentration       0.15
alphaCutoff            14.0
SASA                   on
surfaceTension         0.005

PME                    off
wrapAll                off

timestep               2.0
rigidBonds             all
nonbondedFreq          1
fullElectFrequency     1
stepspercycle          20

outputName             minimize
outputEnergies         100
restartfreq            1000

minimize               10000
```

运行：

```bash
namd3 +p16 minimize.conf > minimize.log 2>&1
```

检查结束和异常：

```bash
tail -20 minimize.log
grep -Ei 'FATAL ERROR|ERROR:|nan|Segmentation' minimize.log
awk '/^ENERGY:/ {print $2,$12}' minimize.log | head -5
awk '/^ENERGY:/ {print $2,$12}' minimize.log | tail -10
```

本项目 10000 步后势能约在 5178 kcal/mol 附近形成平台。最初 1–2 步出现少量：

```text
MINIMIZER SLOWLY MOVING 2 ATOMS WITH BAD CONTACTS DOWNHILL
```

如果只出现在最开始，随后能量正常下降、没有 `nan`、没有 `GIVING UP`，通常是最小化正在修复初始碰撞，不等同于最终结果有问题。

若后期仍反复出现 bad contacts，或能量为 `-99999999999.9999`、`nan`，应停止并重新检查坐标，不应单纯增加最小化步数。

## 7. HMR：为 4 fs 时间步长重新分配质量

### 7.1 原理和作用

HMR（hydrogen mass repartitioning）把与氢相连的重原子的一部分质量转移给氢，使高频 X–H 振动变慢。体系总质量保持不变，电荷、原子类型、键和势能参数不变。

本项目把氢质量设为 3.024 Da，并配合：

```namd
timestep       4.0
rigidBonds     all
rigidTolerance 1.0e-8
```

HMR 的直接收益是：在稳定的前提下，4 fs 每一步对应的物理时间是 2 fs 的两倍，因此达到同样模拟时间大约只需一半步数。

HMR 不是“自动加速所有动力学”的魔法，也不保证任意体系在 4 fs 都稳定，所以必须经过短测试和温度检查。你提供的文献中“partitioned the mass of heavy atoms into the bonded hydrogen atoms”就是 HMR 的描述。

### 7.2 生成 HMR PSF

创建 `make_hmr.tcl`：

```tcl
package require psfgen
resetpsf
readpsf 2KY10_built.psf
repartitionHMass 3.024
writepsf 2KY10_hmr.psf
quit
```

运行并检查：

```bash
vmd -dispdev text -e make_hmr.tcl > make_hmr.log 2>&1
grep -Ei 'fatal|error|warning|unknown' make_hmr.log
grep '!NATOM' 2KY10_built.psf
grep '!NATOM' 2KY10_hmr.psf
```

检查总质量是否守恒：

```bash
awk '/!NATOM/{n=$1;next} n>0{s+=$8;n--} END{print "Original mass:",s}' 2KY10_built.psf
awk '/!NATOM/{n=$1;next} n>0{s+=$8;n--} END{print "HMR mass:",s}' 2KY10_hmr.psf
```

本项目两者总质量都约为 `67696.8 Da`，原子数都为 9563。

### 7.3 4 fs 稳定性测试

先运行 2500 steps，也就是 10 ps：

```text
2500 steps × 4 fs = 10 ps
```

配置应使用：

```namd
structure              2KY10_hmr.psf 
coordinates            2KY10_built.pdb 
binCoordinates          minimize.coor

timestep               4.0
rigidBonds             all
rigidTolerance         1.0e-8

langevin               on
langevinTemp           280
langevinDamping        1.0
langevinHydrogen       off

# 其余 CHARMM36m、GBIS、cutoff 设置与后续 tiger2_base.namd 保持一致
outputName             hmr4fs_test
outputEnergies         25
restartfreq            2500
DCDfreq                 2500
temperature             280
run                     2500
```

然后进行 100 ps 平衡：

```text
25000 steps × 4 fs = 100 ps
```

可以从 10 ps 测试的 restart 继续：

```namd
coordinates            2KY10_built.pdb
binCoordinates          hmr4fs_test.coor
binVelocities           hmr4fs_test.vel
extendedSystem          hmr4fs_test.xsc

# 已读取速度时不要再用 temperature 重新生成速度
outputName              hmr4fs_eq100ps
run                     25000
```

本项目 100 ps 测试的平均温度约 `284.6 K`，没有 fatal、nan、moving too fast 或 constraint failure，说明当前 HMR/4 fs 设置可进入下一阶段。

检查命令：

```bash
grep -Ei 'FATAL ERROR|ERROR:|nan|moving too fast|constraint failure' hmr4fs_eq100ps.log
awk '/^ENERGY:/ {s+=$13;n++} END {print "Average temperature =",s/n,"K"}' hmr4fs_eq100ps.log
tail -20 hmr4fs_eq100ps.log
```

最终用于 TIGER2 的起始二进制坐标为：

```text
hmr4fs_eq100ps.coor
```

## 8. TIGER2 增强采样原理

普通高温 replica exchange 通常直接比较不同温度的 replicas，replica 数量常随体系自由度增加。TIGER2 的特点是：

1. 多个相同体系的 replicas 在不同温度采样。
2. 每轮结束时所有 replicas 都淬火到相同 baseline 温度。
3. 在相同 baseline 条件下比较构象并用 Monte Carlo 规则决定交换/重排。
4. 高温帮助跨越能垒，baseline ensemble 用于目标温度下的结构统计。

本项目四个温度按指数分布，大致为：

```text
280 K, 315 K, 355 K, 400 K
```

每轮：

```text
500 steps heating/equilibration
+ 12000 steps sampling
+ 2500 steps quenching to baseline
= 15000 steps
= 60 ps per replica at 4 fs
```

TIGER2 的交换对象和温度位置会变化，因此分析时不能把“replica 0 文件”永久等同于 280 K。必须结合 `.history` 文件按照 `replica(loc)`/温度位置拆分 baseline ensemble。

## 9. TIGER2 配置文件之间的关系

### 9.1 `tiger2_base.namd`

保存所有 replicas 共用的 NAMD 物理设置：

```namd
structure              input/2KY10_hmr.psf
coordinates            input/2KY10_built.pdb

paraTypeCharmm         on
parameters             /home/selp/igem-2026/CHARMM_toppar/par_all36m_prot.prm

exclude                scaled1-4
oneFourScaling         1.0

switching              on
switchdist             15.0
cutoff                 16.0
pairlistdist           18.0

timestep               4.0
rigidBonds             all
rigidTolerance         1.0e-8
nonbondedFreq          1
fullElectFrequency     1
stepspercycle          20

wrapAll                off
PME                    off

langevinPiston         off
langevin               on
langevinDamping        1.0
langevinHydrogen       off

GBIS                   on
solventDielectric      78.5
ionConcentration       0.15
alphaCutoff            14.0
SASA                   on
surfaceTension         0.005

outputEnergies         500
binaryOutput           yes
```

不要在此文件中固定 `temperature`、`langevinTemp`、`outputName` 或 `run`；这些由 TIGER2 脚本为每个 replica 动态设置。

也不要在此文件中写死 `binCoordinates`。新模拟的初始二进制坐标和断点续跑坐标必须由 `tiger2_2ky10.namd` 按运行状态选择，否则 restart 坐标可能被旧起始坐标覆盖。

### 9.2 `tiger2_100ns.conf`

保存本次正式采样方案：

```tcl
set num_replicas 4
set min_temp 280
set max_temp 400

set steps_equil1 500
set steps_sample 12000
set steps_equil2 2500

set num_runs 417
set runs_per_frame 5
set frames_per_restart 5

set namd_config_file "tiger2_base.namd"
set initial_coordinates "input/hmr4fs_eq100ps.coor"
set output_root "production/%s/tiger2-prod"

source ./tiger2_2ky10.namd
```

`runs_per_frame × frames_per_restart = 25`，所以每 25 cycles 写一组 restart。

### 9.3 `tiger2_2ky10.namd`

这是 multi-copy 算法主体，负责：

- 读取 replica 编号和总数。
- 指数分配温度。
- 控制每轮 heating、sampling 和 quenching。
- 使用 `replicaBarrier` 同步 replicas。
- 交换势能、温度和位置数据。
- 使用 Monte Carlo 准则决定交换。
- 写 `.history`、DCD 和 restart 文件。
- 在断点续跑时恢复 `i_run`、`i_step` 和 replica 状态。

当前项目版本包含几项必要兼容修复：

- restart 时先保存 restart Tcl 路径，避免 `source` 后变量被覆盖。
- restart 后 history 使用 append，避免覆盖前一段历史。
- 修复旧 restart 清理语句。
- `EX_ratio` 使用浮点除法，并避免除以零。

不要随意用网上的旧脚本覆盖当前项目版本。

### 9.4 `tiger2_test.conf`

与正式参数基本相同，但只运行 2 cycles。它用于一次性验证：

- 4 replicas 能同时启动。
- GBIS 在 netlrts-smp 下不崩溃。
- replicas 能通过 barrier。
- 一轮交换逻辑可以完成。
- 输出目录、DCD、history 和 restart 可写。

正式模拟前必须先通过这个测试。

### 9.5 `gbis_netlrts_single.conf`

如果 multi-copy 在 `calcGBIS` 附近崩溃，先用 netlrts-smp 做单副本诊断：

```namd
temperature             280
langevinTemp            280
outputName              output/gbis-netlrts-single
binCoordinates          input/hmr4fs_eq100ps.coor
source                   tiger2_base.namd
DCDfreq                  5000
restartfreq              5000
run                      30000
```

如果单副本也崩溃，优先检查 GBIS、坐标、NAMD build 或 HMR；如果单副本正常而 multi-copy 崩溃，再检查启动方式和 replica 脚本。

## 10. 正式 TIGER2 运行

### 10.1 准备输入

```bash
cd ~/igem-2026/MD/TIGER2_2KY10
mkdir -p input output/{0,1,2,3}

cp ../2KY10_hmr.psf input/
cp ../2KY10_built.pdb input/
cp ../hmr4fs_eq100ps.coor input/
```

### 10.2 两轮测试

```bash
chmod +x run_tiger2_test.sh
./run_tiger2_test.sh
```

正确的 netlrts-smp 启动结构是：

```bash
../NAMD_3.0.2_Linux-x86_64-netlrts-smp/charmrun \
../NAMD_3.0.2_Linux-x86_64-netlrts-smp/namd3 \
++local ++n 4 ++ppn 1 \
+replicas 4 tiger2_test.conf \
+stdout 'output/%d/tiger2_test.%d.log'
```

含义：

- `++n 4`：总共启动 4 个 SMP 进程。
- `++ppn 1`：每个进程一个 worker。
- `+replicas 4`：划分为 4 个 replicas。
- 每个进程另有一个通信线程，因此系统中会看到额外线程。

通过条件：

```bash
grep -H -E 'TIGER2:|EX_ratio|End of program' output/*/tiger2_test.*.log | tail -40
grep -H -Ei 'FATAL ERROR|ERROR:|nan|constraint failure|moving too fast|Stack Traceback|calcGBIS|Segmentation' output/*/tiger2_test.*.log
```

四个日志都必须出现 `End of program`，第二条检查命令应没有输出。

### 10.3 正式 417 cycles

```bash
chmod +x run_tiger2_100ns.sh
nohup ./run_tiger2_100ns.sh > tiger2_100ns_launcher.log 2>&1 &
echo $! > tiger2_100ns.pid
```

断开浏览器或 SSH 后，`nohup` 启动的 NAMD 仍应继续运行。JupyterLab 的 WebSocket 断线并不自动等同于 NAMD 停止，应以进程和日志为准。

## 11. 实时查看进度

### 11.1 看 NAMD 是否仍在运行

```bash
ps -eo pid,ppid,etime,%cpu,%mem,cmd | grep -E '[n]amd3|[c]harmrun'
```

正常正式运行通常看到：

- 1 个 `charmrun`。
- 4 个 `namd3`。
- 每个 `namd3` 约占用一个 CPU 核心，即约 100% CPU。

实时刷新：

```bash
watch -n 5 "ps -eo pid,ppid,etime,%cpu,%mem,cmd | grep -E '[n]amd3|[c]harmrun'"
```

按 `Ctrl+C` 只会退出 `watch`，不会停止后台 NAMD。

### 11.2 看四条 replicas 的最新步数

新模拟：

```bash
for f in production/*/tiger2_prod.*.log; do
  printf '%s latest_step=' "$f"
  awk '/^ENERGY:/{s=$2} END{print s+0}' "$f"
done
```

从 cycle 50 续跑时：

```bash
for f in production/*/tiger2_resume50.*.log; do
  printf '%s latest_step=' "$f"
  awk '/^ENERGY:/{s=$2} END{print s+0}' "$f"
done
```

四个步数应该接近并持续增长。TIGER2 在 barrier 处同步，所以短时间内略有差异正常，长期差距很大则需要检查。

### 11.3 把步数换算成进度

```bash
s=$(awk '/^ENERGY:/{s=$2} END{print s+0}' \
production/0/tiger2_resume50.0.log)

awk -v s="$s" 'BEGIN {
  printf "Latest step: %d / 6255000\n", s
  printf "Completed cycles: %.1f / 417\n", s/15000
  printf "Per replica: %.3f ns\n", s*0.000004
  printf "Four-replica aggregate: %.3f ns\n", s*0.000016
  printf "Total progress: %.2f%%\n", 100*s/6255000
}'
```

换算关系：

```text
cycle = step / 15000
ns per replica = step × 4 fs / 1,000,000 = step × 0.000004
aggregate ns = ns per replica × 4
progress = step / 6,255,000 × 100%
```

### 11.4 判断日志是否真的在更新

```bash
stat -c '%y  %s bytes  %n' production/*/*.log
```

隔几分钟再次运行。修改时间和字节数增长说明日志仍在写入。

## 12. 断电后的断点续跑

### 12.1 restart 文件必须成套存在

每条 replica 的一个完整 checkpoint 包含：

```text
*.tcl
*.coor
*.vel
*.xsc
```

检查 cycle 50：

```bash
for r in 0 1 2 3; do
  ls -lh production/$r/tiger2-prod.job0.restart50.$r.{tcl,coor,vel,xsc}
done
```

四条 replicas 都必须存在完整文件。不要把某条 replica 的 cycle 50 与另一条的 cycle 25 混用。

本项目 cycle 50 对应：

```text
50 × 15000 = 750000 steps
3.00 ns per replica
12.00 ns aggregate
```

### 12.2 cycle 50 续跑配置

`tiger2_resume50.conf`：

```tcl
set restart_name "production/%s/tiger2-prod.job0.restart50"
source ./tiger2_100ns.conf
```

启动：

```bash
nohup ../NAMD_3.0.2_Linux-x86_64-netlrts-smp/charmrun \
../NAMD_3.0.2_Linux-x86_64-netlrts-smp/namd3 \
++local ++n 4 ++ppn 1 \
+replicas 4 tiger2_resume50.conf \
+stdout 'production/%d/tiger2_resume50.%d.log' \
> tiger2_resume50_launcher.log 2>&1 &

echo $! > tiger2_resume50.pid
```

正确恢复时，四个新日志应出现：

```text
Info: FIRST TIMESTEP 750000
TIGER2: Running Equilibration
```

之后最新 `ENERGY:` step 应大于 750000 并持续增长。

### 12.3 为什么日志里仍能搜到旧 fatal

`+stdout` 对已存在的 replica 日志可能继续追加。若之前使用相同文件名失败过，对整个文件执行 `grep FATAL` 会同时找到旧错误，即使当前运行已经成功。

只检查最后一次 `FIRST TIMESTEP` 之后的内容：

```bash
for f in production/*/tiger2_resume50.*.log; do
  echo "===== $f ====="
  awk '
    /FIRST TIMESTEP/ {buf=""; active=1}
    active {buf=buf $0 ORS}
    END {printf "%s",buf}
  ' "$f" | grep -Ei 'FATAL ERROR|ERROR:|nan|Stack Traceback|calcGBIS|Segmentation'
done
```

没有输出表示最近一次启动段没有检测到这些错误。

更稳妥的日常做法是每次尝试使用新的日志前缀，例如 `resume50_try2`，避免不同尝试混在同一个文件中。

### 12.4 续跑轨迹分析注意事项

cycle 50 断点续跑后：

- `job0` 是断电前的数据。
- 新续跑通常写入 `job1`。
- 如果断电前 `job0` 已经写到 cycle 50 之后，但最近完整 checkpoint 仍是 cycle 50，那么 job0 中 cycle 50 后的部分属于未被续接的分支。
- 正式分析应保留 job0 到 cycle 50，再接 job1；不能把重复区间都计算进去。

## 13. 结果检查与可视化

### 13.1 VMD 加载轨迹

文本模式示例：

```tcl
mol new input/2KY10_hmr.psf type psf waitfor all
mol addfile production/0/tiger2-prod.job0.0.dcd type dcd waitfor all
```

图形界面操作：

1. 先加载 `2KY10_hmr.psf`。
2. 再把对应 replica 的 DCD 作为 trajectory 加到同一个 molecule。
3. 使用 `NewCartoon` 看整体构象。
4. 使用 `Licorice` 或 `CPK` 检查局部异常。
5. 播放轨迹观察是否出现瞬间断链、原子飞散或不合理塌缩。

PSF 与 DCD 的原子数和原子顺序必须一致。

### 13.2 不能只看最后一帧

至少分析：

- 势能随 cycle 的变化。
- 温度层级访问次数和交换接受情况。
- radius of gyration（Rg）。
- N 端到 C 端距离。
- RMSD 或成对结构距离。
- 二级结构比例。
- baseline ensemble 的构象聚类。

对长而柔性的 SELP，单纯 RMSD 可能很大且难以解释，Rg、end-to-end distance 和结构聚类通常更有信息。

### 13.3 baseline ensemble 拆分

每个 replica 的 `.history` 记录 step、温度位置、温度和势能。因为 replicas 会交换位置：

```text
replica 文件编号 != 永久固定温度
```

应按 `.history` 中的 baseline 位置筛选对应 DCD 帧，得到连续的 280 K ensemble。不能把 `production/0` 目录简单当成全部 280 K 数据。

### 13.4 聚类和代表构象

参考文献流程是在平衡后的 baseline replica ensemble 上进行 K-means 聚类，并使用约 6 Å RMSD 阈值。对当前较短的 417-cycle 试验，可以：

1. 丢弃前期未平衡部分，例如先保守丢弃前 20%–50%。
2. 对剩余 baseline 帧计算 Rg、end-to-end distance 和 RMSD。
3. 检查结果是否已出现稳定分布，而不是持续单向漂移。
4. 聚类并选择高占比簇的中心结构。
5. 同时保留多个代表构象，以反映柔性蛋白的构象异质性。

由于本项目的 100.08 ns 是 aggregate 时间，远短于文献中的长程采样，结论应描述为“有限采样下的代表构象”，不能声称已经完全收敛。

## 14. 向粗粒化模拟交接

推荐流程：

```text
TIGER2 baseline ensemble
  -> 去除未平衡区间
  -> 聚类
  -> 选 1–3 个代表全原子构象
  -> 导出无氢 PDB
  -> martinize2 / Martini 3
  -> 单链短程 CG 验证
  -> 比较 CG 与全原子 Rg
  -> 再扩展到多链、交联或更长 CG 生产模拟
```

不要直接用完全伸展初始 PDB 建立最终 CG 生产体系；否则粗粒化结果会强烈继承人工构建的初始几何。

CG 前至少确认：

- 单链、750 residues，链 ID 连续。
- 没有重复原子或断裂主链。
- PDB 原子和残基命名可被 `martinize2` 识别。
- 已移除全原子氢。
- 全原子参考 Rg 和 end-to-end distance 已记录。

## 15. 常见错误与处理

| 错误信息/现象 | 原因 | 处理 |
|---|---|---|
| `No such file or directory` 解压失败 | 当前目录或压缩包名错误 | 先 `pwd; ls -lh`，复制真实文件名 |
| `libamdhip64.so.6` 缺失 | 下载了 HIP 版但没有匹配的 ROCm | 使用 CPU multicore/netlrts-smp，或正确安装 ROCm |
| `No simulation config file specified` | 只运行了 `namd3` | 这是安装成功的表现；提供 `.conf` 即可 |
| PDB/PSF atoms not the same | 原始无氢 PDB 配了含氢 PSF | 使用同一次 psfgen 输出的 built PSF/PDB |
| `UNABLE TO FIND ANGLE PARAMETERS FOR HB2 CT1 NH3` | topology/parameter 版本不匹配，或 PSF 原子类型来自另一套力场 | 用兼容的 `top_all36_prot.rtf` + `par_all36m_prot.prm` 重建 PSF |
| `UNKNOWN PARAMETER ... toppar_water_ions.str` | 把含 CHARMM 命令的 stream 文件直接交给 NAMD parameter reader | 当前 GBIS 不加载该文件；显式水时使用 NAMD 可读参数 |
| `coordinates not found` | 配置缺少 `coordinates` | 始终保留匹配的 PDB `coordinates`，二进制坐标用 `binCoordinates` 覆盖 |
| `langevinTemp is required` | `langevin on` 但未设置热浴温度 | 单副本设置 `langevinTemp`；TIGER2 由脚本动态设置 |
| `Multiple definitions of paraTypeCharmm` | 同一个配置链重复定义不可重复选项 | 只在 base 文件定义一次 |
| `number of steps must be a multiple of stepsPerCycle` | `run` 步数不能整除 `stepspercycle` | 调整 `run` 或 `stepspercycle` |
| `Unknown command-line option +mergegrids` | 当前 NAMD build 不支持该选项 | 从启动脚本删除该选项 |
| `Unable to open extended system file` | restart `.xsc` 路径拼接错误或文件缺失 | 检查 `.tcl/.coor/.vel/.xsc` 四件套和格式化路径 |
| `Segmentation fault` + `calcGBIS` | GBIS/坐标/build/multi-copy 组合问题 | 先跑相同 build 的单副本 GBIS 诊断，再检查 multi-copy |
| JupyterLab 很卡但终端正常 | 浏览器 WebSocket、输出渲染或多终端连接问题 | 用 SSH/系统终端管理后台任务；少用 `tail -f` 显示巨量输出 |
| `WebSocketClosedError` | Jupyter 浏览器连接断开 | 不代表 nohup NAMD 一定停止；用 `ps` 和日志确认 |
| 日志 grep 仍看到 fatal | 同名日志追加了旧失败记录 | 检查最后一个 `FIRST TIMESTEP` 之后，或换新日志名 |

## 16. 每阶段通过清单

### 结构构建

- [ ] 序列长度为 750 aa。
- [ ] 初始 PDB 没有大量重复 XYZ。
- [ ] `2KY10_built.psf` 和 `2KY10_built.pdb` 都是 9563 atoms。
- [ ] 没有 unknown residue/patch。
- [ ] VMD 中没有明显断链或重叠结构。

### 最小化

- [ ] NAMD 正常 `End of program`。
- [ ] 没有 fatal、nan、segmentation fault。
- [ ] 势能总体下降并接近平台。
- [ ] bad contacts 只在早期短暂出现。

### HMR/4 fs

- [ ] HMR 前后原子数相同。
- [ ] HMR 前后总质量相同。
- [ ] 10 ps 测试无 constraint failure/moving too fast。
- [ ] 100 ps 平衡无异常，平均温度接近目标温度。

### TIGER2 测试

- [ ] 单副本 netlrts-smp/GBIS 测试通过。
- [ ] 四个 replica 都启动。
- [ ] 四个测试日志都出现 `End of program`。
- [ ] 可以写 history、DCD 和 restart。
- [ ] 没有 fatal、nan、calcGBIS stack trace。

### 正式生产与续跑

- [ ] 1 个 charmrun + 4 个 namd3 进程存在。
- [ ] 四个最新 step 持续增长且大致同步。
- [ ] restart 每 25 cycles 成套写出。
- [ ] 断电续跑的 `FIRST TIMESTEP` 与 checkpoint 匹配。
- [ ] 分析时去除 checkpoint 后重复的旧分支。

### 结果分析

- [ ] 使用 history 拆分 baseline ensemble。
- [ ] 丢弃未平衡区间。
- [ ] 检查 Rg、end-to-end、能量和温度交换。
- [ ] 使用聚类中心而不是任意最后一帧。
- [ ] 明确报告 100.08 ns 是 aggregate 时间。

## 17. 建议归档的复现实验材料

最终至少保存：

```text
原始氨基酸序列
原始 Chimera PDB
build_psf.tcl
2KY10_built.psf / 2KY10_built.pdb
top_all36_prot.rtf / par_all36m_prot.prm 的版本信息
minimize.conf / minimize.log / minimize.coor
make_hmr.tcl / 2KY10_hmr.psf
hmr4fs_test.conf / hmr4fs_eq100ps.conf / 对应日志和 restart
完整 TIGER2 配置目录
NAMD、VMD 的准确版本和安装包名称
所有 replica 的 log、history、DCD、restart
断电和续跑记录
分析脚本、图、CSV 和最终代表构象
```

论文或报告的方法部分应明确写出：力场、溶剂模型、盐浓度、HMR 目标质量、时间步长、温控参数、replica 数、温度范围、每个 cycle 的三个阶段、cycles 数、每 replica 时间、aggregate 时间、平衡区间和聚类方法。

## 18. 当前项目状态

截至 2026-07-15，本项目已经完成：

- 750 aa 初始结构和匹配的 9563-atom PSF/PDB。
- CHARMM36m + GBIS 10000 步能量最小化。
- HMR PSF（3.024 Da）和总质量守恒检查。
- 4 fs 短程测试与 100 ps 平衡。
- netlrts-smp 单副本 GBIS 诊断。
- 4 replicas、2 cycles TIGER2 测试。
- 417 cycles 正式配置。
- cycle 50 checkpoint 检查和断电续跑配置。

当前续跑的关键识别信息应为：

```text
FIRST TIMESTEP 750000
target step 6255000
target cycle 417
```

下一阶段是在正式采样完成后，按 history 拆分 baseline ensemble、检查收敛趋势、聚类并导出粗粒化候选构象。
