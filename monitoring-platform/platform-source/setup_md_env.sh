#!/bin/bash
# MD 环境配置脚本
# 适用于 igem-2026 项目

set -e  # 遇到错误立即退出

echo "=== MD 环境配置脚本 ==="
echo "开始配置 VMD 和 NAMD 环境..."

# 获取用户主目录
HOME_DIR="$HOME"
PROJECT_DIR="$HOME_DIR/igem-2026"

# 1. 创建项目目录结构
echo "1. 创建项目目录结构..."
mkdir -p "$PROJECT_DIR/MD"
mkdir -p "$PROJECT_DIR/CHARMM_toppar"

# 2. 配置 VMD 环境
echo "2. 配置 VMD 环境..."
VMD_HOME="$PROJECT_DIR/vmd-1.9.4a57"

# 检查 VMD 是否已安装
if [ -d "$VMD_HOME" ] && [ -x "$VMD_HOME/bin/vmd" ]; then
    echo "   VMD 已安装: $VMD_HOME"
    
    # 添加到 ~/.bashrc（如果不存在）
    if ! grep -q "VMD_HOME" ~/.bashrc 2>/dev/null; then
        echo "" >> ~/.bashrc
        echo "# MD VMD 环境配置" >> ~/.bashrc
        echo "export VMD_HOME=\"$VMD_HOME\"" >> ~/.bashrc
        echo "export PATH=\"\$VMD_HOME/bin:\$PATH\"" >> ~/.bashrc
        echo "   已添加 VMD 环境变量到 ~/.bashrc"
    else
        echo "   VMD 环境变量已存在于 ~/.bashrc"
    fi
    
    # 立即生效
    export VMD_HOME="$VMD_HOME"
    export PATH="$VMD_HOME/bin:$PATH"
else
    echo "   警告: VMD 未安装或路径不正确: $VMD_HOME"
    echo "   请先安装 VMD 1.9.4a57"
fi

# 3. 配置 NAMD 环境
echo "3. 配置 NAMD 环境..."
NAMD_MC="$PROJECT_DIR/MD/NAMD_3.0.2_Linux-x86_64-multicore"
NAMD_SMP="$PROJECT_DIR/MD/NAMD_3.0.2_Linux-x86_64-netlrts-smp"

# 检查 NAMD 是否已安装
if [ -d "$NAMD_MC" ] && [ -d "$NAMD_SMP" ]; then
    echo "   NAMD multicore: $NAMD_MC"
    echo "   NAMD netlrts-smp: $NAMD_SMP"
    
    # 添加到 ~/.bashrc（如果不存在）
    if ! grep -q "NAMD_MC" ~/.bashrc 2>/dev/null; then
        echo "" >> ~/.bashrc
        echo "# MD NAMD 环境配置" >> ~/.bashrc
        echo "export NAMD_MC=\"$NAMD_MC\"" >> ~/.bashrc
        echo "export NAMD_SMP=\"$NAMD_SMP\"" >> ~/.bashrc
        echo "export PATH=\"\$NAMD_MC:\$PATH\"" >> ~/.bashrc
        echo "   已添加 NAMD 环境变量到 ~/.bashrc"
    else
        echo "   NAMD 环境变量已存在于 ~/.bashrc"
    fi
    
    # 立即生效
    export NAMD_MC="$NAMD_MC"
    export NAMD_SMP="$NAMD_SMP"
    export PATH="$NAMD_MC:$PATH"
else
    echo "   警告: NAMD 未安装或路径不正确"
    echo "   请确保以下目录存在:"
    echo "     - $NAMD_MC"
    echo "     - $NAMD_SMP"
fi

# 4. 配置 CHARMM 力场文件路径
echo "4. 配置 CHARMM 力场文件路径..."
CHARMM_TOPPAR="$PROJECT_DIR/CHARMM_toppar"

# 检查关键力场文件是否存在
if [ -d "$CHARMM_TOPPAR" ]; then
    echo "   CHARMM 拓扑目录: $CHARMM_TOPPAR"
    
    # 检查关键文件
    REQUIRED_FILES=(
        "top_all36_prot.rtf"
        "par_all36m_prot.prm"
    )
    
    for file in "${REQUIRED_FILES[@]}"; do
        if [ -f "$CHARMM_TOPPAR/$file" ]; then
            echo "   ✓ 找到 $file"
        else
            echo "   ✗ 缺失 $file"
        fi
    done
    
    # 添加到 ~/.bashrc（如果不存在）
    if ! grep -q "CHARMM_TOPPAR" ~/.bashrc 2>/dev/null; then
        echo "" >> ~/.bashrc
        echo "# MD CHARMM 力场文件路径" >> ~/.bashrc
        echo "export CHARMM_TOPPAR=\"$CHARMM_TOPPAR\"" >> ~/.bashrc
        echo "   已添加 CHARMM_TOPPAR 环境变量到 ~/.bashrc"
    else
        echo "   CHARMM_TOPPAR 环境变量已存在于 ~/.bashrc"
    fi
    
    # 立即生效
    export CHARMM_TOPPAR="$CHARMM_TOPPAR"
else
    echo "   警告: CHARMM 拓扑目录不存在: $CHARMM_TOPPAR"
fi

# 5. 验证环境配置
echo "5. 验证环境配置..."

# 验证 VMD
if command -v vmd &> /dev/null; then
    echo "   ✓ VMD 命令可用"
else
    echo "   ✗ VMD 命令不可用"
fi

# 验证 NAMD
if command -v namd3 &> /dev/null; then
    echo "   ✓ NAMD3 命令可用"
else
    echo "   ✗ NAMD3 命令不可用"
fi

# 验证 charmrun（用于 TIGER2 多副本）
if [ -f "$NAMD_SMP/charmrun" ]; then
    echo "   ✓ charmrun 可用"
else
    echo "   ✗ charmrun 不可用"
fi

# 6. 显示服务器信息
echo "6. 服务器硬件信息..."
echo "   CPU 核心数: $(nproc)"
echo "   内存信息:"
free -h | grep -E "^Mem:|^Swap:" | awk '{print "     " $1 ": " $2 " total, " $3 " used, " $4 " free"}'

echo ""
echo "=== 环境配置完成 ==="
echo ""
echo "使用说明:"
echo "1. 重新加载配置: source ~/.bashrc"
echo "2. 验证 VMD: vmd -dispdev text"
echo "3. 验证 NAMD: namd3 +p1"
echo "4. 验证 charmrun: ls -lh \$NAMD_SMP/charmrun"
echo ""
echo "下一步:"
echo "1. 确保所有软件安装包已解压到正确位置"
echo "2. 下载 CHARMM36m 力场文件到 $CHARMM_TOPPAR"
echo "3. 按照 MD 全流程指南开始模拟"