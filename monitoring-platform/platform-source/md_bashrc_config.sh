#!/bin/bash
# Molecular Dynamics Platform 环境配置 - 直接添加到 ~/.bashrc 的内容
# 将以下内容添加到 ~/.bashrc 文件末尾

# Molecular Dynamics Platform 项目环境配置
# 项目根目录
export MD_ROOT="$HOME/igem-2026/MD"

# VMD 环境配置
export VMD_HOME="$HOME/igem-2026/vmd-1.9.4a57"
export PATH="$VMD_HOME/bin:$PATH"

# NAMD 环境配置
export NAMD_MC="$HOME/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-multicore"
export NAMD_SMP="$HOME/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-netlrts-smp"
export PATH="$NAMD_MC:$PATH"

# CHARMM 力场文件路径
export CHARMM_TOPPAR="$HOME/igem-2026/CHARMM_toppar"

# TIGER2 项目目录（如果需要）
export TIGER2_DIR="$HOME/igem-2026/MD/TIGER2_2KY10"

# 工作目录快捷方式
alias cd-md="cd $MD_ROOT"
alias cd-tiger2="cd $TIGER2_DIR"

# 验证函数
check_md_platform_env() {
    echo "=== Molecular Dynamics Platform 环境检查 ==="
    echo "VMD: $(command -v vmd 2>/dev/null || echo '未找到')"
    echo "NAMD: $(command -v namd3 2>/dev/null || echo '未找到')"
    echo "charmrun: $([ -f "$NAMD_SMP/charmrun" ] && echo '可用' || echo '未找到')"
    echo ""
    echo "CPU 核心数: $(nproc)"
    echo "内存信息:"
    free -h | grep "^Mem:" | awk '{print "  " $2 " total, " $3 " used, " $4 " free"}'
    echo ""
    echo "CHARMM 力场文件:"
    for file in top_all36_prot.rtf par_all36m_prot.prm; do
        if [ -f "$CHARMM_TOPPAR/$file" ]; then
            echo "  ✓ $file"
        else
            echo "  ✗ $file"
        fi
    done
}