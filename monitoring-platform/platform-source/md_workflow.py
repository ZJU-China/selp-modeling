#!/usr/bin/env python3
"""
Molecular Dynamics Platform 交互式工作流脚本
选择步骤、检查文件、执行命令
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime


# ============================================================
# 配置
# ============================================================

MD_ROOT = Path(os.environ.get("MD_ROOT", Path.home() / "igem-2026" / "MD"))
TIGER2_DIR = MD_ROOT / "TIGER2_2KY10"
CHARMM_DIR = Path.home() / "igem-2026" / "CHARMM_toppar"

# 文件名约定
FILES = {
    "input_pdb": "2KY10.pdb",
    "top_rtf": CHARMM_DIR / "top_all36_prot.rtf",
    "par_prm": CHARMM_DIR / "par_all36m_prot.prm",
    "built_psf": "2KY10_built.psf",
    "built_pdb": "2KY10_built.pdb",
    "hmr_psf": "2KY10_hmr.psf",
    "min_coor": "minimize.coor",
    "test_coor": "hmr4fs_test.coor",
    "eq_coor": "hmr4fs_eq100ps.coor",
}


# ============================================================
# 工具函数
# ============================================================

def clear():
    os.system("clear" if os.name != "nt" else "cls")


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_step(num, title, status=""):
    icon = "✓" if status == "done" else "○" if status == "" else "✗"
    print(f"  {icon} 步骤 {num}: {title}")


def check_file(name, label, required=True):
    path = MD_ROOT / name if not isinstance(name, Path) else name
    exists = path.exists()
    if exists:
        size = path.stat().st_size
        print(f"    ✓ {label}: {path.name} ({size:,} bytes)")
    else:
        if required:
            print(f"    ✗ {label}: {path.name} (缺失)")
        else:
            print(f"    - {label}: {path.name} (可选)")
    return exists


def run_command(cmd, description, log_file=None):
    print(f"\n  执行: {description}")
    print(f"  命令: {cmd}")
    print(f"  {'-'*50}")

    if log_file:
        with open(log_file, "w") as f:
            result = subprocess.run(cmd, shell=True, stdout=f, stderr=subprocess.STDOUT)
    else:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
        if result.stderr:
            print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)

    if result.returncode == 0:
        print(f"  ✓ 完成 (返回码: {result.returncode})")
    else:
        print(f"  ✗ 失败 (返回码: {result.returncode})")

    return result.returncode == 0


# ============================================================
# 步骤定义
# ============================================================

def step1_build_psf():
    """结构构建"""
    print_header("步骤 1: 结构构建 (psfgen)")

    print("\n  检查输入文件:")
    if not check_file(FILES["input_pdb"], "初始 PDB"):
        print("\n  ❌ 缺少初始 PDB 文件，无法继续")
        return False
    if not check_file(FILES["top_rtf"], "CHARMM 拓扑"):
        print("\n  ❌ 缺少 CHARMM 拓扑文件，无法继续")
        return False

    print(f"\n  输出文件:")
    print(f"    → {FILES['built_psf']}")
    print(f"    → {FILES['built_pdb']}")

    confirm = input("\n  执行构建? (y/n): ").strip().lower()
    if confirm != "y":
        print("  已取消")
        return False

    os.chdir(MD_ROOT)
    script = Path("scripts/tcl/build_2KY10_psf.tcl")
    if not script.exists():
        script = MD_ROOT.parent / "igem-2026-software" / "scripts" / "tcl" / "build_2KY10_psf.tcl"

    cmd = f'vmd -dispdev text -e {script} > build_psf.log 2>&1'
    success = run_command(cmd, "VMD psfgen", "build_psf.log")

    if success:
        check_file(FILES["built_psf"], "输出 PSF")
        check_file(FILES["built_pdb"], "输出 PDB")

    return success


def step2_make_hmr():
    """HMR 处理"""
    print_header("步骤 2: 氢质量重分配 (HMR)")

    print("\n  检查输入文件:")
    if not check_file(FILES["built_psf"], "输入 PSF"):
        print("\n  ❌ 需先完成步骤 1")
        return False

    print(f"\n  当前 HMR 质量: 3.024 Da")
    mass = input("  输入新质量 (回车保持 3.024): ").strip()
    if not mass:
        mass = "3.024"

    print(f"\n  输出文件:")
    print(f"    → {FILES['hmr_psf']}")

    confirm = input("\n  执行 HMR? (y/n): ").strip().lower()
    if confirm != "y":
        print("  已取消")
        return False

    os.chdir(MD_ROOT)

    # 临时修改 make_hmr.tcl 中的质量
    script = MD_ROOT.parent / "igem-2026-software" / "scripts" / "tcl" / "make_hmr.tcl"
    if not script.exists():
        script = MD_ROOT / "make_hmr.tcl"

    if mass != "3.024" and script.exists():
        content = script.read_text()
        content = content.replace("hmassrepart mass 3.024", f"hmassrepart mass {mass}")
        tmp_script = MD_ROOT / "make_hmr_tmp.tcl"
        tmp_script.write_text(content)
        script = tmp_script

    cmd = f'vmd -dispdev text -e {script} > make_hmr.log 2>&1'
    success = run_command(cmd, "VMD HMR", "make_hmr.log")

    if success:
        check_file(FILES["hmr_psf"], "输出 HMR PSF")

    # 清理临时文件
    tmp = MD_ROOT / "make_hmr_tmp.tcl"
    if tmp.exists():
        tmp.unlink()

    return success


def step3_minimize():
    """能量最小化"""
    print_header("步骤 3: 能量最小化")

    print("\n  检查输入文件:")
    if not check_file(FILES["built_psf"], "PSF"):
        return False
    if not check_file(FILES["built_pdb"], "PDB"):
        return False
    if not check_file(FILES["par_prm"], "CHARMM 参数"):
        return False

    steps = input("\n  最小化步数 (回车保持 10000): ").strip()
    if not steps:
        steps = "10000"

    cores = input("  并行核心数 (回车保持 16): ").strip()
    if not cores:
        cores = "16"

    print(f"\n  输出文件:")
    print(f"    → minimize.coor")
    print(f"    → minimize.log")

    confirm = input("\n  执行最小化? (y/n): ").strip().lower()
    if confirm != "y":
        return False

    os.chdir(MD_ROOT)
    script = MD_ROOT / "scripts" / "namd" / "minimize.conf"
    if not script.exists():
        script = MD_ROOT.parent / "igem-2026-software" / "scripts" / "namd" / "minimize.conf"

    cmd = f'namd3 +p{cores} {script} > minimize.log 2>&1'
    success = run_command(cmd, f"NAMD 最小化 ({steps} 步)", "minimize.log")

    if success:
        check_file(MD_ROOT / "minimize.coor", "输出坐标")

    return success


def step4_hmr_test():
    """4fs 稳定性测试"""
    print_header("步骤 4: HMR + 4fs 稳定性测试")

    print("\n  检查输入文件:")
    if not check_file(FILES["hmr_psf"], "HMR PSF"):
        print("\n  ❌ 需先完成步骤 2")
        return False
    if not check_file(FILES["built_pdb"], "PDB"):
        return False
    if not check_file(MD_ROOT / FILES["min_coor"], "最小化坐标", required=False):
        print("\n  提示: 使用 minimize.coor 或 gbis_test.coor")

    coor = input("\n  坐标文件 (回车使用 minimize.coor): ").strip()
    if not coor:
        coor = "minimize.coor"

    print(f"\n  输出文件:")
    print(f"    → hmr4fs_test.coor")
    print(f"    → hmr4fs_test.log")

    confirm = input("\n  执行测试? (y/n): ").strip().lower()
    if confirm != "y":
        return False

    os.chdir(MD_ROOT)

    # 创建临时配置
    config = MD_ROOT / "hmr4fs_test_tmp.conf"
    template = MD_ROOT.parent / "igem-2026-software" / "scripts" / "namd" / "hmr4fs_test.conf"
    if template.exists():
        content = template.read_text()
        content = content.replace("binCoordinates     gbis_test.coor", f"binCoordinates     {coor}")
        config.write_text(content)

    cmd = f'namd3 +p16 {config} > hmr4fs_test.log 2>&1'
    success = run_command(cmd, "4fs 稳定性测试 (10 ps)", "hmr4fs_test.log")

    if success:
        check_file(MD_ROOT / "hmr4fs_test.coor", "输出坐标")

    if config.exists():
        config.unlink()

    return success


def step5_hmr_eq():
    """100 ps 平衡"""
    print_header("步骤 5: HMR + 4fs 100 ps 平衡")

    print("\n  检查输入文件:")
    if not check_file(FILES["hmr_psf"], "HMR PSF"):
        return False
    if not check_file(FILES["built_pdb"], "PDB"):
        return False
    if not check_file(MD_ROOT / "hmr4fs_test.coor", "测试坐标"):
        print("\n  ❌ 需先完成步骤 4")
        return False

    print(f"\n  输出文件:")
    print(f"    → hmr4fs_eq100ps.coor (TIGER2 起始坐标)")
    print(f"    → hmr4fs_eq100ps.log")

    confirm = input("\n  执行平衡? (y/n): ").strip().lower()
    if confirm != "y":
        return False

    os.chdir(MD_ROOT)
    script = MD_ROOT / "scripts" / "namd" / "hmr4fs_eq100ps.conf"
    if not script.exists():
        script = MD_ROOT.parent / "igem-2026-software" / "scripts" / "namd" / "hmr4fs_eq100ps.conf"

    cmd = f'namd3 +p16 {script} > hmr4fs_eq100ps.log 2>&1'
    success = run_command(cmd, "100 ps 平衡", "hmr4fs_eq100ps.log")

    if success:
        check_file(MD_ROOT / "hmr4fs_eq100ps.coor", "输出坐标")

    return success


def step6_tiger2_test():
    """TIGER2 测试"""
    print_header("步骤 6: TIGER2 两轮测试")

    print("\n  检查输入文件:")
    input_dir = TIGER2_DIR / "input"
    if not input_dir.exists():
        input_dir.mkdir(parents=True, exist_ok=True)
        print("  创建 input 目录...")

    for name in ["2KY10_hmr.psf", "2KY10_built.pdb", "hmr4fs_eq100ps.coor"]:
        src = MD_ROOT / name
        dst = input_dir / name
        if src.exists() and not dst.exists():
            import shutil
            shutil.copy2(src, dst)
            print(f"  复制 {name} 到 input/")

    check_file(input_dir / "2KY10_hmr.psf", "HMR PSF")
    check_file(input_dir / "2KY10_built.pdb", "PDB")
    check_file(input_dir / "hmr4fs_eq100ps.coor", "起始坐标")

    print(f"\n  输出目录:")
    print(f"    → TIGER2_2KY10/output/{{0,1,2,3}}/")

    confirm = input("\n  执行 TIGER2 测试 (2 cycles)? (y/n): ").strip().lower()
    if confirm != "y":
        return False

    os.chdir(TIGER2_DIR)
    script = TIGER2_DIR / "run_tiger2_test.sh"
    if not script.exists():
        print("  创建 run_tiger2_test.sh...")
        script.write_text('''#!/usr/bin/env bash
set -euo pipefail
mkdir -p output/{0,1,2,3}
NAMD_DIR="../NAMD_3.0.2_Linux-x86_64-netlrts-smp"
"$NAMD_DIR/charmrun" "$NAMD_DIR/namd3" \\
  ++local ++n 4 ++ppn 1 +replicas 4 tiger2_test.conf \\
  +stdout 'output/%d/tiger2_test.%d.log'
''')
        script.chmod(0o755)

    cmd = f'bash {script}'
    success = run_command(cmd, "TIGER2 两轮测试")

    if success:
        print("\n  检查输出:")
        for r in range(4):
            log = TIGER2_DIR / "output" / str(r) / "tiger2_test.0.log"
            if log.exists():
                with open(log) as f:
                    content = f.read()
                    if "End of program" in content:
                        print(f"    ✓ Replica {r}: End of program")
                    else:
                        print(f"    ✗ Replica {r}: 未正常结束")

    return success


def step7_tiger2_production():
    """TIGER2 正式运行"""
    print_header("步骤 7: TIGER2 正式生产")

    print("\n  检查输入文件:")
    input_dir = TIGER2_DIR / "input"
    for name in ["2KY10_hmr.psf", "2KY10_built.pdb", "hmr4fs_eq100ps.coor"]:
        check_file(input_dir / name, name)

    # 读取当前配置
    config_file = TIGER2_DIR / "tiger2_100ns.conf"
    if not config_file.exists():
        config_file = Path.home() / "igem-2026" / "igem-2026-software" / "scripts" / "namd" / "tiger2_100ns.conf"

    current_num_runs = 417
    if config_file.exists():
        with open(config_file) as f:
            for line in f:
                if line.strip().startswith("set num_runs"):
                    current_num_runs = int(line.split()[-1])

    print("\n  当前参数:")
    print("    num_replicas = 4")
    print("    min_temp = 280 K, max_temp = 400 K")
    per_replica_ns = current_num_runs * 60 / 1000
    total_ns = per_replica_ns * 4
    print(f"    num_runs = {current_num_runs} ({per_replica_ns:.2f} ns/replica)")
    print(f"    总时间 = {total_ns:.2f} ns aggregate")

    # 交互修改 num_runs
    print(f"\n  {'─'*50}")
    print("  调整 num_runs:")
    print("    - 每 cycle = 60 ps (15000 steps × 4 fs)")
    print("    - 常用值: 100(6ns), 200(12ns), 417(25ns), 500(30ns)")
    print(f"    - 输入 0 保持当前值 ({current_num_runs})")

    new_num_runs = input(f"\n  输入新的 num_runs (回车保持 {current_num_runs}): ").strip()

    if new_num_runs and new_num_runs.isdigit():
        new_num_runs = int(new_num_runs)
        if new_num_runs == 0:
            new_num_runs = current_num_runs
    else:
        new_num_runs = current_num_runs

    # 显示新的模拟时间
    new_per_replica = new_num_runs * 60 / 1000
    new_total = new_per_replica * 4
    print(f"\n  新配置:")
    print(f"    num_runs = {new_num_runs}")
    print(f"    每 replica = {new_per_replica:.2f} ns")
    print(f"    总 aggregate = {new_total:.2f} ns")

    # 更新配置文件
    if new_num_runs != current_num_runs:
        update = input(f"\n  更新 tiger2_100ns.conf? (y/n): ").strip().lower()
        if update == "y":
            # 读取模板
            template_file = Path.home() / "igem-2026" / "igem-2026-software" / "scripts" / "namd" / "tiger2_100ns.conf"
            if template_file.exists():
                content = template_file.read_text()
                content = content.replace(f"set num_runs {current_num_runs}", f"set num_runs {new_num_runs}")

                # 写入到 TIGER2 目录
                with open(TIGER2_DIR / "tiger2_100ns.conf", "w") as f:
                    f.write(content)
                print(f"    ✓ 已更新 tiger2_100ns.conf")

    print(f"\n  输出目录:")
    print(f"    → TIGER2_2KY10/production/{{0,1,2,3}}/")

    confirm = input("\n  启动正式运行 (nohup)? (y/n): ").strip().lower()
    if confirm != "y":
        return False

    os.chdir(TIGER2_DIR)

    cmd = (
        'nohup ../NAMD_3.0.2_Linux-x86_64-netlrts-smp/charmrun '
        '../NAMD_3.0.2_Linux-x86_64-netlrts-smp/namd3 '
        '++local ++n 4 ++ppn 1 +replicas 4 tiger2_100ns.conf '
        "+stdout 'production/%d/tiger2_prod.%d.log' "
        '> tiger2_100ns_launcher.log 2>&1 &'
    )
    success = run_command(cmd, "TIGER2 正式生产")

    if success:
        # 获取 PID
        import time
        time.sleep(1)
        pid_cmd = "pgrep -f 'tiger2_100ns.conf'"
        result = subprocess.run(pid_cmd, shell=True, capture_output=True, text=True)
        if result.stdout.strip():
            pid = result.stdout.strip().split("\n")[0]
            (TIGER2_DIR / "tiger2_100ns.pid").write_text(pid)
            print(f"\n  ✓ 已启动, PID: {pid}")
            print(f"  使用以下命令监控:")
            print(f"    watch -n 10 'ps aux | grep namd3'")
            print(f"    python3 tiger2/monitor_tiger2.py production")

    return success


def step8_resume():
    """断点续跑"""
    print_header("步骤 8: 断点续跑")

    # 查找最近的 restart
    restarts = {}
    for r in range(4):
        replica_dir = TIGER2_DIR / "production" / str(r)
        for f in replica_dir.glob("*.restart*.tcl"):
            match = f.stem.split("restart")[-1].split(".")[0]
            try:
                cycle = int(match)
                if cycle not in restarts:
                    restarts[cycle] = 0
                restarts[cycle] += 1
            except:
                pass

    if not restarts:
        print("\n  ✗ 未找到 restart 文件")
        return False

    # 找完整的 restart (4 个 replica 都有)
    complete = {c: n for c, n in restarts.items() if n == 4}
    if not complete:
        print("\n  ✗ 无完整的 restart (需要 4 条 replica)")
        print(f"    找到: {restarts}")
        return False

    print("\n  可用的 restart points:")
    for cycle in sorted(complete.keys()):
        step = cycle * 15000
        time_ns = step * 4 / 1e6
        print(f"    Cycle {cycle}: step {step:,}, {time_ns:.2f} ns")

    cycle = input("\n  选择 cycle 编号: ").strip()
    if not cycle or not cycle.isdigit():
        return False
    cycle = int(cycle)

    if cycle not in complete:
        print(f"  ✗ Cycle {cycle} 不完整")
        return False

    print(f"\n  从 cycle {cycle} 续跑...")

    # 创建续跑配置
    config = TIGER2_DIR / f"tiger2_resume{cycle}.conf"
    config.write_text(f'set restart_name "production/%s/tiger2-prod.job0.restart{cycle}"\nsource ./tiger2_100ns.conf\n')

    cmd = (
        f'nohup ../NAMD_3.0.2_Linux-x86_64-netlrts-smp/charmrun '
        f'../NAMD_3.0.2_Linux-x86_64-netlrts-smp/namd3 '
        f'++local ++n 4 ++ppn 1 +replicas 4 tiger2_resume{cycle}.conf '
        f"+stdout 'production/%d/tiger2_resume{cycle}.%d.log' "
        f'> tiger2_resume{cycle}_launcher.log 2>&1 &'
    )

    os.chdir(TIGER2_DIR)
    success = run_command(cmd, f"从 cycle {cycle} 续跑")

    if success:
        import time
        time.sleep(1)
        pid_cmd = "pgrep -f 'tiger2_resume'"
        result = subprocess.run(pid_cmd, shell=True, capture_output=True, text=True)
        if result.stdout.strip():
            pid = result.stdout.strip().split("\n")[0]
            print(f"\n  ✓ 已启动续跑, PID: {pid}")

    return success


def step9_monitor():
    """监控模拟"""
    print_header("步骤 9: 模拟监控")

    os.chdir(MD_ROOT)

    # 检查进程
    print("\n  当前 NAMD 进程:")
    result = subprocess.run(
        "ps -eo pid,etime,%cpu,cmd | grep -E '[n]amd3|[c]harmrun'",
        shell=True, capture_output=True, text=True
    )
    if result.stdout.strip():
        print(result.stdout)
    else:
        print("    无运行中的 NAMD 进程")

    # 检查进度
    monitor_script = Path(__file__).parent / "tiger2" / "monitor_tiger2.py"
    if not monitor_script.exists():
        monitor_script = Path(__file__).parent / "monitor_tiger2.py"

    if monitor_script.exists():
        print("\n  调用监控脚本...")
        subprocess.run(f"python3 {monitor_script} TIGER2_2KY10/production", shell=True)
    else:
        # 简单监控
        print("\n  各 Replica 最新步数:")
        for r in range(4):
            log_dir = TIGER2_DIR / "production" / str(r)
            logs = sorted(log_dir.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
            if logs:
                with open(logs[0]) as f:
                    for line in f:
                        if line.startswith("ENERGY:"):
                            parts = line.split()
                            if len(parts) >= 2:
                                step = int(parts[1])
                                time_ns = step * 4 / 1e6
                                print(f"    Replica {r}: step {step:,} ({time_ns:.2f} ns)")

    input("\n  按回车返回菜单...")
    return True


def step10_analyze():
    """分析脚本"""
    print_header("步骤 10: 结果分析")

    print("\n  可用分析:")
    print("    1. TIGER2 历史分析 (温度交换/能量)")
    print("    2. 轨迹分析 (Rg, 端到端距离)")
    print("    3. 构象聚类")
    print("    4. 检查 PSF/PDB 匹配")
    print("    5. 查看步数对应时间")

    choice = input("\n  选择 (1-5): ").strip()

    python_dir = Path.home() / "igem-2026" / "igem-2026-software" / "scripts" / "python"

    if choice == "1":
        cmd = f"conda run -n igem2026 python3 {python_dir}/analyze_history.py TIGER2_2KY10/production"
        subprocess.run(cmd, shell=True, cwd=MD_ROOT)
    elif choice == "2":
        psf = input("  PSF 文件 (回车使用 input/2KY10_hmr.psf): ").strip()
        if not psf:
            psf = "TIGER2_2KY10/input/2KY10_hmr.psf"
        dcd = input("  DCD 文件: ").strip()
        if dcd:
            cmd = f"conda run -n igem2026 python3 {python_dir}/analyze_trajectory.py {psf} {dcd}"
            subprocess.run(cmd, shell=True, cwd=MD_ROOT)
    elif choice == "3":
        psf = input("  PSF 文件 (回车使用 input/2KY10_hmr.psf): ").strip()
        if not psf:
            psf = "TIGER2_2KY10/input/2KY10_hmr.psf"
        dcd = input("  DCD 文件: ").strip()
        n = input("  聚类数 (回车使用 5): ").strip()
        if not n:
            n = "5"
        if dcd:
            cmd = f"conda run -n igem2026 python3 {python_dir}/cluster_conformations.py {psf} {dcd} {n}"
            subprocess.run(cmd, shell=True, cwd=MD_ROOT)
    elif choice == "4":
        psf = input("  PSF 文件 (回车使用 2KY10_built.psf): ").strip()
        if not psf:
            psf = "2KY10_built.psf"
        pdb = input("  PDB 文件 (回车使用 2KY10_built.pdb): ").strip()
        if not pdb:
            pdb = "2KY10_built.pdb"
        cmd = f"conda run -n igem2026 python3 {python_dir}/utils.py check {psf} {pdb}"
        subprocess.run(cmd, shell=True, cwd=MD_ROOT)
    elif choice == "5":
        step = input("  步数: ").strip()
        if step:
            cmd = f"conda run -n igem2026 python3 {python_dir}/utils.py time {step} 4.0"
            subprocess.run(cmd, shell=True, cwd=MD_ROOT)

    input("\n  按回车返回菜单...")
    return True


# ============================================================
# 主菜单
# ============================================================

def show_status():
    """显示当前状态"""
    print("\n  项目状态:")
    checks = [
        (FILES["input_pdb"], "初始 PDB"),
        (FILES["built_psf"], "构建 PSF"),
        (FILES["built_pdb"], "构建 PDB"),
        (FILES["hmr_psf"], "HMR PSF"),
        (MD_ROOT / FILES["min_coor"], "最小化坐标"),
        (MD_ROOT / FILES["eq_coor"], "平衡坐标"),
    ]
    for name, label in checks:
        path = MD_ROOT / name if not isinstance(name, Path) else name
        status = "✓" if path.exists() else "✗"
        print(f"    {status} {label}")


def main_menu():
    while True:
        clear()
        print_header("MD 工作流控制台")
        show_status()

        print(f"\n  {'─'*50}")
        print("  结构准备:")
        print_step(1, "结构构建 (psfgen)")
        print_step(2, "氢质量重分配 (HMR)")

        print(f"\n  模拟:")
        print_step(3, "能量最小化")
        print_step(4, "4fs 稳定性测试")
        print_step(5, "100 ps 平衡")

        print(f"\n  TIGER2:")
        print_step(6, "两轮测试")
        print_step(7, "正式生产 (417 cycles)")
        print_step(8, "断点续跑")

        print(f"\n  工具:")
        print_step(9, "监控模拟状态")
        print_step(10, "结果分析")

        print(f"\n  {'─'*50}")
        print("  0. 退出")

        choice = input("\n  选择步骤 (0-10): ").strip()

        if choice == "0":
            print("\n  再见!")
            break
        elif choice == "1":
            step1_build_psf()
        elif choice == "2":
            step2_make_hmr()
        elif choice == "3":
            step3_minimize()
        elif choice == "4":
            step4_hmr_test()
        elif choice == "5":
            step5_hmr_eq()
        elif choice == "6":
            step6_tiger2_test()
        elif choice == "7":
            step7_tiger2_production()
        elif choice == "8":
            step8_resume()
        elif choice == "9":
            step9_monitor()
        elif choice == "10":
            step10_analyze()
        else:
            print("  无效选择")

        input("\n  按回车继续...")


if __name__ == "__main__":
    main_menu()
