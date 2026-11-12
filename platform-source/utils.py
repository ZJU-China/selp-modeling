#!/usr/bin/env python3
"""
MD 工具函数集
常用的数据处理和文件操作工具
"""

import numpy as np
from pathlib import Path


def extract_coordinates_from_psf(psf_file):
    """
    从 PSF 文件提取原子信息
    """
    atoms = []
    in_natom = False
    natom = 0
    
    with open(psf_file, 'r') as f:
        for line in f:
            if '!NATOM' in line:
                natom = int(line.split()[0])
                in_natom = True
                continue
            
            if in_natom and natom > 0:
                parts = line.split()
                if len(parts) >= 7:
                    atoms.append({
                        'id': int(parts[0]),
                        'segid': parts[1],
                        'resid': int(parts[2]),
                        'resname': parts[3],
                        'name': parts[4],
                        'type': parts[5],
                        'charge': float(parts[6]),
                    })
                natom -= 1
                if natom == 0:
                    break
    
    return atoms


def calculate_mass_from_psf(psf_file):
    """
    从 PSF 计算总质量
    """
    atoms = extract_coordinates_from_psf(psf_file)
    
    # 原子质量映射 (近似值)
    mass_map = {
        'H': 1.008, 'HE': 4.003, 'C': 12.011, 'N': 14.007,
        'O': 15.999, 'S': 32.06, 'P': 30.974
    }
    
    total_mass = 0.0
    for atom in atoms:
        element = atom['name'][0]
        if element in mass_map:
            total_mass += mass_map[element]
        else:
            total_mass += 12.0  # 默认碳
    
    return total_mass


def check_psf_pdb_match(psf_file, pdb_file):
    """
    检查 PSF 和 PDB 原子数是否匹配
    """
    # 统计 PSF 原子数
    psf_count = 0
    with open(psf_file, 'r') as f:
        for line in f:
            if '!NATOM' in line:
                psf_count = int(line.split()[0])
                break
    
    # 统计 PDB 原子数
    pdb_count = 0
    with open(pdb_file, 'r') as f:
        for line in f:
            if line.startswith(('ATOM', 'HETATM')):
                pdb_count += 1
    
    print(f"PSF 原子数: {psf_count}")
    print(f"PDB 原子数: {pdb_count}")
    print(f"匹配: {'是' if psf_count == pdb_count else '否'}")
    
    return psf_count == pdb_count


def convert_step_to_time(step, timestep_fs=4.0):
    """
    将步数转换为模拟时间
    """
    time_fs = step * timestep_fs
    time_ps = time_fs / 1000.0
    time_ns = time_ps / 1000.0
    
    return {
        'step': step,
        'time_fs': time_fs,
        'time_ps': time_ps,
        'time_ns': time_ns
    }


def format_time(time_ps):
    """
    格式化时间输出
    """
    if time_ps < 1000:
        return f"{time_ps:.2f} ps"
    else:
        return f"{time_ps/1000:.3f} ns"


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python utils.py check <psf> <pdb>")
        print("  python utils.py mass <psf>")
        print("  python utils.py time <step> [timestep_fs]")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "check" and len(sys.argv) >= 4:
        check_psf_pdb_match(sys.argv[2], sys.argv[3])
    elif action == "mass" and len(sys.argv) >= 3:
        mass = calculate_mass_from_psf(sys.argv[2])
        print(f"总质量: {mass:.2f} Da")
    elif action == "time" and len(sys.argv) >= 3:
        step = int(sys.argv[2])
        timestep = float(sys.argv[3]) if len(sys.argv) > 3 else 4.0
        result = convert_step_to_time(step, timestep)
        print(f"Step {step} = {format_time(result['time_ps'])}")
    else:
        print("未知命令")
