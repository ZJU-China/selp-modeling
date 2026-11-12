"""Trajectory file download + merge (moved from backend/services/trajectory-sync.js).

Downloads the topology PDB/PSF and ALL per-replica DCD segments (paths
discovered by the tasktype's own trajectory-info logic) into the task's local
cache/trajectory dir, then merges each replica's segments (fresh run + resumed
jobs) into a single replica_{r}.dcd with one frame per simulated cycle.
"""
import os

from lib import trajectory_info, dcd_merge


def handle(ssh, cfg, args, local_task):
    if args.sub and args.sub != "sync":
        return {"ok": False, "error": f"unknown trajectory sub {args.sub!r}"}

    info = trajectory_info.discover(ssh, cfg)
    if not info or not info.get("pdb"):
        return {"ok": False, "error": "no topology PDB found"}

    trajectory_cfg = (cfg.extra.get("trajectory") or {})
    preview_max_frames = int(trajectory_cfg.get("previewMaxFrames", dcd_merge.PREVIEW_MAX_FRAMES))
    tail_window = int(trajectory_cfg.get("tailWindowCycles", dcd_merge.TAIL_WINDOW_CYCLES))

    cache = os.path.join(local_task, "cache", "trajectory")
    segments_dir = os.path.join(cache, "segments")
    preview_dir = os.path.join(cache, "preview")
    last100_dir = os.path.join(cache, "last100")
    os.makedirs(segments_dir, exist_ok=True)
    os.makedirs(last100_dir, exist_ok=True)

    pdb_local = os.path.join(cache, "topology.pdb")
    if not trajectory_info.download_trajectory_pdb(ssh, info["pdb"], pdb_local):
        return {"ok": False, "error": "PDB download failed"}
    pdb_size = os.path.getsize(pdb_local)

    if info.get("psf"):
        trajectory_info.download_trajectory_pdb(ssh, info["psf"], os.path.join(cache, "topology.psf"))

    replica_sizes = []
    replica_frames = []
    preview_sizes = []
    last100_sizes = []
    last100_frames = []
    for r in range(cfg.num_replicas):
        segs = (info.get("dcds") or {}).get(str(r)) or []
        if not segs:
            replica_sizes.append(0)
            replica_frames.append(0)
            preview_sizes.append(0)
            last100_sizes.append(0)
            last100_frames.append(0)
            continue

        seg_local = []
        ok = True
        for i, remote_dcd in enumerate(segs):
            local = os.path.join(segments_dir, f"replica_{r}.seg{i}.dcd")
            if not trajectory_info.download_trajectory_pdb(ssh, remote_dcd, local) or not os.path.exists(local):
                ok = False
                break
            seg_local.append(local)

        if not ok:
            replica_sizes.append(0)
            replica_frames.append(0)
            preview_sizes.append(0)
            last100_sizes.append(0)
            last100_frames.append(0)
            continue

        merged_path = os.path.join(cache, f"replica_{r}.dcd")
        preview_path = os.path.join(preview_dir, f"replica_{r}.dcd")
        try:
            merged = dcd_merge.merge_segments(
                seg_local,
                os.path.join(local_task, "logs", str(r)),
                merged_path,
                steps_per_cycle=cfg.steps_per_cycle,
            )
            replica_sizes.append(os.path.getsize(merged_path) if os.path.exists(merged_path) else 0)
            replica_frames.append(merged["frames"])
            # Viewer preview: downsampled DCD (fast browser load). Best-effort.
            preview_size = 0
            try:
                dcd_merge.subsample_dcd(merged_path, preview_path, max_frames=preview_max_frames)
                if os.path.exists(preview_path):
                    preview_size = os.path.getsize(preview_path)
            except Exception:
                preview_size = 0
            preview_sizes.append(preview_size)
            # Convergence page: last-100-cycles tail trajectory. Best-effort.
            last100_path = os.path.join(last100_dir, f"replica_{r}.dcd")
            last100_size = 0
            last100_nf = 0
            try:
                tail = dcd_merge.tail_dcd(merged_path, last100_path, n_frames=tail_window)
                if os.path.exists(last100_path):
                    last100_size = os.path.getsize(last100_path)
                    last100_nf = tail["frames"]
            except Exception:
                last100_size = 0
                last100_nf = 0
            last100_sizes.append(last100_size)
            last100_frames.append(last100_nf)
        except Exception:
            replica_sizes.append(0)
            replica_frames.append(0)
            preview_sizes.append(0)
            last100_sizes.append(0)
            last100_frames.append(0)
        finally:
            for local in seg_local:
                try:
                    os.remove(local)
                except OSError:
                    pass

    return {"ok": True, "pdbSize": pdb_size, "replicaSizes": replica_sizes, "replicaFrames": replica_frames, "previewSizes": preview_sizes, "last100Sizes": last100_sizes, "last100Frames": last100_frames}
