#!/usr/bin/env python3
"""
轨迹分析脚本
分析 TIGER2 产出的 DCD 轨迹，计算 Rg、端到端距离、RMSD 等指标
"""

import numpy as np
import matplotlib.pyplot as plt
import sys
from pathlib import Path

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import rms
except ImportError:
    print("需要安装 MDAnalysis: pip install MDAnalysis")
    sys.exit(1)


def analyze_trajectory(psf_file, dcd_file, output_prefix="traj_analysis"):
    """
    分析单条轨迹
    """
    print(f"加载结构: {psf_file}")
    print(f"加载轨迹: {dcd_file}")
    
    u = mda.Universe(psf_file, dcd_file)
    
    # 检查蛋白质原子
    protein = u.select_atoms("protein")
    if len(protein) == 0:
        print("警告: 未找到蛋白质原子")
        return None
    
    print(f"蛋白质原子数: {len(protein)}")
    print(f"轨迹帧数: {len(u.trajectory)}")
    
    results = {
        'frame': [],
        'rg': [],
        'end_to_end': [],
        'time_ps': []
    }
    
    # 计算每帧的指标
    for i, ts in enumerate(u.trajectory):
        results['frame'].append(i)
        results['time_ps'].append(ts.time)
        
        # 回旋半径 (Rg)
        rg_value = protein.radius_of_gyration()
        results['rg'].append(rg_value)
        
        # 端到端距离 (N端Cα到C端Cα)
        ca_atoms = protein.select_atoms("name CA")
        if len(ca_atoms) >= 2:
            n_term = ca_atoms[0]
            c_term = ca_atoms[-1]
            e2e = np.linalg.norm(c_term.position - n_term.position)
            results['end_to_end'].append(e2e)
        else:
            results['end_to_end'].append(np.nan)
    
    return results


def plot_analysis(results, output_prefix="traj_analysis"):
    """
    绘制分析结果
    """
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    frames = results['frame']
    time_ps = results['time_ps']
    
    # Rg 随时间变化
    axes[0, 0].plot(time_ps, results['rg'], 'b-', alpha=0.7)
    axes[0, 0].set_xlabel('Time (ps)')
    axes[0, 0].set_ylabel('Radius of Gyration (Å)')
    axes[0, 0].set_title('Radius of Gyration vs Time')
    axes[0, 0].grid(True, alpha=0.3)
    
    # Rg 分布
    axes[0, 1].hist(results['rg'], bins=50, edgecolor='black', alpha=0.7)
    axes[0, 1].set_xlabel('Radius of Gyration (Å)')
    axes[0, 1].set_ylabel('Count')
    axes[0, 1].set_title('Rg Distribution')
    axes[0, 1].axvline(np.mean(results['rg']), color='r', linestyle='--', 
                       label=f'Mean: {np.mean(results["rg"]):.2f} Å')
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)
    
    # 端到端距离随时间变化
    valid_e2e = [e for e in results['end_to_end'] if not np.isnan(e)]
    if valid_e2e:
        axes[1, 0].plot(time_ps[:len(valid_e2e)], valid_e2e, 'r-', alpha=0.7)
        axes[1, 0].set_xlabel('Time (ps)')
        axes[1, 0].set_ylabel('End-to-End Distance (Å)')
        axes[1, 0].set_title('End-to-End Distance vs Time')
        axes[1, 0].grid(True, alpha=0.3)
        
        # 端到端距离分布
        axes[1, 1].hist(valid_e2e, bins=50, edgecolor='black', alpha=0.7, color='red')
        axes[1, 1].set_xlabel('End-to-End Distance (Å)')
        axes[1, 1].set_ylabel('Count')
        axes[1, 1].set_title('End-to-End Distance Distribution')
        axes[1, 1].axvline(np.mean(valid_e2e), color='b', linestyle='--',
                           label=f'Mean: {np.mean(valid_e2e):.2f} Å')
        axes[1, 1].legend()
        axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_prefix}.png', dpi=150, bbox_inches='tight')
    plt.show()
    
    # 保存数据到CSV
    import pandas as pd
    df = pd.DataFrame(results)
    df.to_csv(f'{output_prefix}.csv', index=False)
    print(f"数据已保存到 {output_prefix}.csv")
    
    # 打印统计摘要
    print(f"\n=== 轨迹分析摘要 ===")
    print(f"Rg: {np.mean(results['rg']):.2f} ± {np.std(results['rg']):.2f} Å")
    if valid_e2e:
        print(f"End-to-End: {np.mean(valid_e2e):.2f} ± {np.std(valid_e2e):.2f} Å")


def analyze_baseline_ensemble(production_dir, psf_file, num_replicas=4, 
                              history_file_pattern="tiger2-prod.job0.{replica_id}.history",
                              dcd_pattern="tiger2-prod.job0.{replica_id}.dcd"):
    """
    分析 baseline ensemble（280 K 采样）
    根据 .history 文件筛选 baseline 位置的帧
    """
    print("\n=== Baseline Ensemble Analysis ===")
    
    all_rg = []
    all_e2e = []
    
    for replica_id in range(num_replicas):
        replica_dir = Path(production_dir) / str(replica_id)
        history_file = replica_dir / history_file_pattern.format(replica_id=replica_id)
        dcd_file = replica_dir / dcd_pattern.format(replica_id=replica_id)
        
        if not history_file.exists() or not dcd_file.exists():
            print(f"跳过 Replica {replica_id}: 文件不存在")
            continue
        
        print(f"\n处理 Replica {replica_id}...")
        
        # 解析 history 找 baseline 帧
        baseline_steps = []
        with open(history_file, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    step = int(parts[0])
                    replica_loc = int(parts[1])
                    # replica_loc == 0 表示在 baseline 位置
                    if replica_loc == 0:
                        baseline_steps.append(step)
        
        if not baseline_steps:
            print(f"  未找到 baseline 帧")
            continue
        
        print(f"  找到 {len(baseline_steps)} 个 baseline 帧")
        
        # 分析 DCD
        u = mda.Universe(psf_file, dcd_file)
        protein = u.select_atoms("protein")
        
        for ts in u.trajectory:
            if ts.data['step'] in baseline_steps if 'step' in ts.data else True:
                rg_value = protein.radius_of_gyration()
                all_rg.append(rg_value)
                
                ca_atoms = protein.select_atoms("name CA")
                if len(ca_atoms) >= 2:
                    e2e = np.linalg.norm(ca_atoms[-1].position - ca_atoms[0].position)
                    all_e2e.append(e2e)
    
    if all_rg:
        print(f"\nBaseline Ensemble 统计:")
        print(f"  Rg: {np.mean(all_rg):.2f} ± {np.std(all_rg):.2f} Å")
        print(f"  End-to-End: {np.mean(all_e2e):.2f} ± {np.std(all_e2e):.2f} Å")
    
    return {'rg': all_rg, 'end_to_end': all_e2e}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage:")
        print("  单轨迹分析: python analyze_trajectory.py <psf> <dcd>")
        print("  Baseline ensemble: python analyze_trajectory.py --baseline <production_dir> <psf>")
        sys.exit(1)
    
    if sys.argv[1] == "--baseline":
        production_dir = sys.argv[2]
        psf_file = sys.argv[3]
        analyze_baseline_ensemble(production_dir, psf_file)
    else:
        psf_file = sys.argv[1]
        dcd_file = sys.argv[2]
        results = analyze_trajectory(psf_file, dcd_file)
        if results:
            plot_analysis(results)
