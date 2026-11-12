#!/usr/bin/env python3
"""
构象聚类脚本
对 TIGER2 baseline ensemble 进行 K-means 聚类，选择代表构象
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

try:
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
except ImportError:
    print("需要安装 scikit-learn: pip install scikit-learn")
    sys.exit(1)


def extract_frames(psf_file, dcd_file, max_frames=None):
    """
    从 DCD 提取坐标用于聚类
    """
    u = mda.Universe(psf_file, dcd_file)
    protein = u.select_atoms("protein and name CA")
    
    frames = []
    for i, ts in enumerate(u.trajectory):
        if max_frames and i >= max_frames:
            break
        frames.append(protein.positions.copy())
    
    return np.array(frames), u


def cluster_conformations(coordinates, n_clusters=5):
    """
    对构象进行 K-means 聚类
    """
    # 将坐标展平为特征向量
    n_frames = coordinates.shape[0]
    n_atoms = coordinates.shape[1]
    X = coordinates.reshape(n_frames, -1)
    
    # 标准化
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # K-means 聚类
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(X_scaled)
    
    return labels, kmeans


def select_representatives(coordinates, labels, method='medoid'):
    """
    选择每个簇的代表构象
    """
    representatives = {}
    unique_labels = np.unique(labels)
    
    for cluster_id in unique_labels:
        mask = labels == cluster_id
        cluster_coords = coordinates[mask]
        
        if method == 'medoid':
            # 选择距离簇中心最近的帧
            center = cluster_coords.mean(axis=0)
            distances = np.linalg.norm(cluster_coords - center, axis=(1, 2))
            medoid_idx = np.where(mask)[0][np.argmin(distances)]
            representatives[cluster_id] = medoid_idx
        elif method == 'centroid':
            # 使用 K-means 中心（不对应实际帧）
            representatives[cluster_id] = None
    
    return representatives


def save_representatives(u, representatives, output_dir="representatives"):
    """
    保存代表构象为 PDB 文件
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    protein = u.select_atoms("protein")
    
    for cluster_id, frame_idx in representatives.items():
        if frame_idx is not None:
            u.trajectory[frame_idx]
            output_file = output_path / f"cluster_{cluster_id}_frame{frame_idx}.pdb"
            protein.write(str(output_file))
            print(f"  Cluster {cluster_id}: frame {frame_idx} -> {output_file}")


def plot_clustering(labels, coordinates, output_prefix="clustering"):
    """
    绘制聚类结果
    """
    from sklearn.decomposition import PCA
    
    # PCA 降维用于可视化
    n_frames = coordinates.shape[0]
    X = coordinates.reshape(n_frames, -1)
    
    pca = PCA(n_components=2)
    X_2d = pca.fit_transform(X)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # 聚类散点图
    scatter = axes[0].scatter(X_2d[:, 0], X_2d[:, 1], c=labels, cmap='tab10', alpha=0.6, s=20)
    axes[0].set_xlabel('PC1')
    axes[0].set_ylabel('PC2')
    axes[0].set_title('Conformation Clustering (PCA)')
    plt.colorbar(scatter, ax=axes[0], label='Cluster')
    
    # 簇大小分布
    unique_labels, counts = np.unique(labels, return_counts=True)
    axes[1].bar(unique_labels, counts)
    axes[1].set_xlabel('Cluster')
    axes[1].set_ylabel('Number of Frames')
    axes[1].set_title('Cluster Population')
    axes[1].grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(f'{output_prefix}.png', dpi=150, bbox_inches='tight')
    plt.show()
    
    # 打印统计
    print("\n=== 聚类统计 ===")
    for label, count in zip(unique_labels, counts):
        print(f"  Cluster {label}: {count} frames ({100*count/len(labels):.1f}%)")


def full_clustering_pipeline(psf_file, dcd_file, n_clusters=5, 
                             baseline_steps=None, output_prefix="conformation_clustering"):
    """
    完整的聚类流程
    """
    print("1. 提取坐标...")
    coordinates, u = extract_frames(psf_file, dcd_file)
    print(f"   提取了 {len(coordinates)} 帧")
    
    print("2. K-means 聚类...")
    labels, kmeans = cluster_conformations(coordinates, n_clusters)
    print(f"   完成 {n_clusters} 个簇的聚类")
    
    print("3. 选择代表构象...")
    representatives = select_representatives(coordinates, labels)
    
    print("4. 保存代表构象...")
    save_representatives(u, representatives)
    
    print("5. 绘制分析图...")
    plot_clustering(labels, coordinates, output_prefix)
    
    return labels, representatives


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python cluster_conformations.py <psf> <dcd> <n_clusters>")
        sys.exit(1)
    
    psf_file = sys.argv[1]
    dcd_file = sys.argv[2]
    n_clusters = int(sys.argv[3])
    
    full_clustering_pipeline(psf_file, dcd_file, n_clusters)
