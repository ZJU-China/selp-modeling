# Molecular Dynamics Platform Scripts 目录说明

## 目录结构

```
scripts/
├── tcl/                    # VMD/psfgen 脚本
│   ├── build_2KY10_psf.tcl    # 构建 PSF/PDB
│   └── make_hmr.tcl           # 生成 HMR PSF
├── namd/                   # NAMD 配置文件
│   ├── minimize.conf           # 能量最小化
│   ├── hmr4fs_test.conf        # 4fs 稳定性测试
│   ├── hmr4fs_eq100ps.conf     # 100ps 平衡
│   ├── gbis_test.conf          # GBIS 诊断
│   ├── tiger2_base.namd        # TIGER2 基础配置
│   ├── tiger2_2ky10.namd       # TIGER2 主脚本
│   ├── tiger2_100ns.conf       # 正式 417 cycles
│   ├── tiger2_test.conf        # 2 cycles 测试
│   └── tiger2_resume50.conf    # 断点续跑配置
└── python/                 # 分析脚本
    ├── analyze_history.py      # TIGER2 历史分析
    ├── analyze_trajectory.py   # 轨迹分析 (Rg, RMSD)
    ├── cluster_conformations.py # 构象聚类
    └── utils.py                # 工具函数
```

## 使用方法

### 1. 结构构建

```bash
cd ~/igem-2026/MD
vmd -dispdev text -e scripts/tcl/build_2KY10_psf.tcl
vmd -dispdev text -e scripts/tcl/make_hmr.tcl
```

### 2. 能量最小化

```bash
namd3 +p16 scripts/namd/minimize.conf > minimize.log 2>&1
```

### 3. HMR 测试

```bash
namd3 +p16 scripts/namd/hmr4fs_test.conf > hmr4fs_test.log 2>&1
namd3 +p16 scripts/namd/hmr4fs_eq100ps.conf > hmr4fs_eq100ps.log 2>&1
```

### 4. TIGER2 模拟

```bash
# 测试运行
./TIGER2_2KY10/run_tiger2_test.sh

# 正式运行
nohup ./TIGER2_2KY10/run_tiger2_100ns.sh > tiger2_100ns_launcher.log 2>&1 &
```

### 5. 分析脚本

```bash
# 激活 conda 环境
conda activate igem2026

# 分析 TIGER2 历史
python scripts/python/analyze_history.py TIGER2_2KY10/production

# 分析轨迹
python scripts/python/analyze_trajectory.py TIGER2_2KY10/input/2KY10_hmr.psf TIGER2_2KY10/production/0/tiger2-prod.job0.0.dcd

# 构象聚类
python scripts/python/cluster_conformations.py TIGER2_2KY10/input/2KY10_hmr.psf TIGER2_2KY10/production/0/tiger2-prod.job0.0.dcd 5

# 检查 PSF/PDB 匹配
python scripts/python/utils.py check 2KY10_built.psf 2KY10_built.pdb

# 查看步数对应时间
python scripts/python/utils.py time 750000 4.0
```

## 依赖

- Python 3.12+
- MDAnalysis
- scikit-learn
- matplotlib
- pandas
- numpy

安装: `conda activate igem2026`
