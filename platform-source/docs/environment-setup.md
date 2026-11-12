# Molecular Dynamics Platform 环境配置说明

## 文件说明

1. `setup_molecular-dynamics-platform_env.sh` - 完整的环境配置脚本（推荐首次使用）
2. `molecular-dynamics-platform_bashrc_config.sh` - 简洁的 ~/.bashrc 配置内容

## 使用方法

### 方法一：运行完整配置脚本（推荐）

```bash
# 1. 赋予执行权限
chmod +x setup_molecular-dynamics-platform_env.sh

# 2. 运行配置脚本
./setup_molecular-dynamics-platform_env.sh

# 3. 重新加载配置
source ~/.bashrc
```

### 方法二：手动添加到 ~/.bashrc

```bash
# 1. 查看配置内容
cat molecular-dynamics-platform_bashrc_config.sh

# 2. 复制内容到 ~/.bashrc
cat molecular-dynamics-platform_bashrc_config.sh >> ~/.bashrc

# 3. 重新加载配置
source ~/.bashrc
```

## 验证配置

```bash
# 检查环境变量
echo $VMD_HOME
echo $NAMD_MC
echo $NAMD_SMP
echo $CHARMM_TOPPAR

# 验证命令可用性
command -v vmd
command -v namd3
ls -lh $NAMD_SMP/charmrun

# 运行环境检查函数（如果使用方法二）
check_molecular-dynamics-platform_env
```

## 前置条件

在运行配置脚本前，请确保：

1. **VMD 已安装**：
   - 位置：`~/igem-2026/vmd-1.9.4a57/`
   - 需要可执行文件：`bin/vmd`

2. **NAMD 已安装**：
   - 单副本版本：`~/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-multicore/`
   - 多副本版本：`~/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-netlrts-smp/`
   - 需要可执行文件：`namd3` 和 `charmrun`

3. **CHARMM 力场文件已下载**：
   - 位置：`~/igem-2026/CHARMM_toppar/`
   - 需要文件：
     - `top_all36_prot.rtf`（蛋白拓扑）
     - `par_all36m_prot.prm`（蛋白参数）

## 目录结构

配置完成后，项目目录结构应为：

```
~/igem-2026/
├── vmd-1.9.4a57/          # VMD 安装目录
├── CHARMM_toppar/          # CHARMM 力场文件
│   ├── top_all36_prot.rtf
│   └── par_all36m_prot.prm
└── MD/                   # 项目主目录
    ├── NAMD_3.0.2_Linux-x86_64-multicore/
    ├── NAMD_3.0.2_Linux-x86_64-netlrts-smp/
    ├── 2KY10.pdb           # 初始结构
    ├── build_psf.tcl       # PSF 构建脚本
    ├── minimize.conf       # 最小化配置
    └── TIGER2_2KY10/       # TIGER2 模拟目录
```

## 常见问题

### Q: 为什么 NAMD 报错 "No simulation config file specified"？

A: 这实际上是好消息，说明 NAMD 已正确安装。只需提供 `.conf` 配置文件即可：

```bash
namd3 +p1 minimize.conf
```

### Q: 如何测试 VMD 是否正常工作？

A: 启动文本模式：

```bash
vmd -dispdev text
# 出现 vmd > 提示符后输入 quit 退出
```

### Q: 服务器没有 GPU，能运行模拟吗？

A: 可以。CPU 版本的 NAMD（multicore 和 netlrts-smp）足以完成当前流程。

### Q: 如何查看服务器硬件信息？

```bash
# CPU 核心数
nproc

# 详细 CPU 信息
lscpu

# 内存信息
free -h
```

## 下一步

配置完成后，按照《Molecular Dynamics Platform Workflow Guide》进行：

1. 准备初始 PDB 结构
2. 运行 `build_psf.tcl` 生成 PSF/PDB
3. 执行能量最小化
4. 进行 HMR 处理
5. 运行 TIGER2 模拟

## 技术支持

如有问题，请参考：
- 《Molecular Dynamics Platform Workflow Guide》第 4 节：安装与环境配置
- 《Molecular Dynamics Platform Workflow Guide》第 15 节：常见错误与处理