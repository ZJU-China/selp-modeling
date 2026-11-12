#!/usr/bin/env python3
"""
TIGER2 History 分析脚本
解析 TIGER2 输出的 .history 文件，分析温度交换和能量分布
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import sys


def parse_history(history_file):
    """
    解析 TIGER2 .history 文件
    
    格式: step replica_loc temperature temp_measured potential_energy
    """
    data = []
    with open(history_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split()
                if len(parts) >= 5:
                    data.append({
                        'step': int(parts[0]),
                        'replica_loc': int(parts[1]),
                        'target_temp': float(parts[2]),
                        'measured_temp': float(parts[3]),
                        'potential_energy': float(parts[4])
                    })
    return pd.DataFrame(data)


def analyze_history(production_dir, num_replicas=4):
    """
    分析所有 replica 的历史文件
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    all_data = {}
    
    for replica_id in range(num_replicas):
        history_file = Path(production_dir) / f"{replica_id}" / f"tiger2-prod.job0.{replica_id}.history"
        if history_file.exists():
            df = parse_history(history_file)
            all_data[replica_id] = df
            
            # 温度交换历史
            axes[0, 0].plot(df['step'], df['target_temp'], label=f'Replica {replica_id}', alpha=0.7)
            
            # 势能分布
            axes[0, 1].hist(df['potential_energy'], bins=50, alpha=0.5, label=f'Replica {replica_id}')
    
    axes[0, 0].set_xlabel('Step')
    axes[0, 0].set_ylabel('Target Temperature (K)')
    axes[0, 0].set_title('Temperature Exchange History')
    axes[0, 0].legend()
    axes[0, 0].grid(True, alpha=0.3)
    
    axes[0, 1].set_xlabel('Potential Energy (kcal/mol)')
    axes[0, 1].set_ylabel('Count')
    axes[0, 1].set_title('Potential Energy Distribution')
    axes[0, 1].legend()
    axes[0, 1].grid(True, alpha=0.3)
    
    # 温度访问频率
    if all_data:
        all_temps = np.concatenate([df['target_temp'].values for df in all_data.values()])
        axes[1, 0].hist(all_temps, bins=30, edgecolor='black')
        axes[1, 0].set_xlabel('Temperature (K)')
        axes[1, 0].set_ylabel('Visit Count')
        axes[1, 0].set_title('Temperature Visit Frequency')
        axes[1, 0].grid(True, alpha=0.3)
    
    # 交换接受率
    exchange_rates = []
    for replica_id, df in all_data.items():
        # 简单估计：温度变化次数
        temp_changes = (df['target_temp'].diff() != 0).sum()
        total_cycles = len(df)
        if total_cycles > 1:
            rate = temp_changes / (total_cycles - 1)
            exchange_rates.append(rate)
    
    if exchange_rates:
        axes[1, 1].bar(range(len(exchange_rates)), exchange_rates)
        axes[1, 1].set_xlabel('Replica')
        axes[1, 1].set_ylabel('Exchange Rate')
        axes[1, 1].set_title('Approximate Exchange Acceptance Rate')
        axes[1, 1].grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig('tiger2_history_analysis.png', dpi=150, bbox_inches='tight')
    plt.show()
    
    # 打印统计摘要
    print("\n=== TIGER2 History Analysis ===")
    for replica_id, df in all_data.items():
        print(f"\nReplica {replica_id}:")
        print(f"  Steps: {df['step'].min()} - {df['step'].max()}")
        print(f"  Temperature range: {df['target_temp'].min():.1f} - {df['target_temp'].max():.1f} K")
        print(f"  Mean potential energy: {df['potential_energy'].mean():.2f} kcal/mol")
        print(f"  Std potential energy: {df['potential_energy'].std():.2f} kcal/mol")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_history.py <production_dir> [num_replicas]")
        sys.exit(1)
    
    production_dir = sys.argv[1]
    num_replicas = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    
    analyze_history(production_dir, num_replicas)
