"""GROMACS CG output pull (called by backend/services/trajectory-sync.js).

Pulls the SSH server's per-sample output files (the XTC trajectory, final and
deformed structures, tpr, edr, cpt) into the task's local output/<sample>/ dir
and reports sizes in the same shape tiger2's trajectory route uses, so the
backend's trajectory-status handling and dashboard degrade gracefully.

The pull is incremental: one remote stat round-trip lists mtimes, and only
files newer than their local copy are transferred. Changed files are streamed
in bulk over a single connection per parent directory as a tar, which keeps a
finished batch (where nothing changes) at one tiny round-trip per 5-minute
sync cycle.
"""
import json
import os
import subprocess
import tarfile


def _remote_name(path):
    return path.rstrip("/").split("/")[-1]


def _remote_samples(ssh, cfg):
    samples = []
    for pattern in cfg.sample_globs():
        pattern = pattern if pattern.endswith("/") else pattern + "/"
        out, _, _ = ssh.exec(f'ls -d {pattern} 2>/dev/null || true', timeout=30)
        for line in out.splitlines():
            line = line.strip().rstrip("/")
            if line:
                samples.append(line)
    return samples


def _stat_command(samples, out_files):
    lines = []
    for sample in samples:
        for f in out_files:
            lines.append(f'[ -f "{sample}/{f}" ] && stat -c "%Y %n" "{sample}/{f}" 2>/dev/null')
    return "\n".join(lines)


def _changed_files(ssh, cfg, samples, out_files, output_dir):
    """Return {full_remote_path: (tar_parent_dir, rel_name)} for files newer
    than their local copy (or missing locally).

    tar_parent_dir is the directory that CONTAINS the sample dir, so a tar
    created with `-C <parent>` extracts as output/<sample>/<file>.
    """
    out, _, _ = ssh.exec(_stat_command(samples, out_files), timeout=90)
    changed = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or " " not in line:
            continue
        mtime_s, path = line.split(" ", 1)
        if not mtime_s.isdigit():
            continue
        name = _remote_name(os.path.dirname(path))
        local = os.path.join(output_dir, name, os.path.basename(path))
        try:
            local_mtime = os.path.getmtime(local)
        except OSError:
            local_mtime = -1
        if int(mtime_s) > local_mtime:
            parent = os.path.dirname(os.path.dirname(path))
            rel = f"{name}/{os.path.basename(path)}"
            changed[path] = (parent, rel)
    return changed


def _stream_tar(ssh, cfg, changed, output_dir):
    by_parent = {}
    for parent, rel in changed.values():
        by_parent.setdefault(parent, []).append(rel)

    tmp = os.path.join(output_dir, ".sync.tar")
    for parent, rels in by_parent.items():
        cmd = (f'cd "{parent}" && tar -cf - '
               + " ".join(f'"{r}"' for r in rels) + " 2>/dev/null")
        if not ssh.download_stream(cmd, tmp, timeout=900):
            return False
        if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            try:
                with tarfile.open(tmp) as t:
                    t.extractall(output_dir, filter="data")
            except (tarfile.TarError, OSError):
                return False
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    return True


def _existing_sizes(local_task):
    """Disk sizes of the already-converted trajectory (steady-state fast path).

    Used when nothing changed and topology.pdb already exists, so the status
    reported to the backend reflects real files instead of triggering a costly
    re-conversion every sync cycle.
    """
    cache = os.path.join(local_task, "cache", "trajectory")

    def _size(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def _replica_sizes(subdir, suffix=".dcd"):
        sizes = []
        i = 0
        while True:
            path = os.path.join(cache, subdir, f"replica_{i}{suffix}")
            if not os.path.exists(path):
                break
            sizes.append(_size(path))
            i += 1
        return sizes

    dcd_sizes = _replica_sizes("")
    last100_sizes = _replica_sizes("last100")
    preview_sizes = _replica_sizes("preview")
    n_replicas = len(dcd_sizes)

    # Real sample names / frame counts come from the conversion sidecar; when
    # absent (pre-upgrade cache) fall back to placeholder replica names.
    meta = {}
    try:
        with open(os.path.join(cache, "meta.json")) as f:
            meta = json.load(f)
    except OSError:
        pass
    samples = meta.get("samples") or [f"replica_{i}" for i in range(n_replicas)]
    preview_frames = meta.get("previewFrames") or [0] * n_replicas
    last100_frames = meta.get("last100Frames") or [0] * n_replicas

    return {
        "ok": True,
        "pdbSize": _size(os.path.join(cache, "topology.pdb")),
        "dcdSize": dcd_sizes[0] if dcd_sizes else 0,
        "dcdSizes": dcd_sizes,
        "previewSizes": preview_sizes,
        "previewFrames": preview_frames,
        "samples": samples,
        "last100Sizes": last100_sizes,
        "last100Frames": last100_frames,
        "existing": True,
    }


def _run_conversion(local_task):
    """Run the MDAnalysis XTC -> PDB/DCD conversion (igem2026 conda env).

    Returns the script's JSON status dict. The route itself runs under the
    system python (no MDAnalysis), so the script is executed with the env's
    interpreter; fall back to `conda run -n igem2026 python3` then PATH.
    The interpreter/conda binaries are overridable via MD_PYTHON_BIN /
    MD_CONDA_BIN env vars (defaults target the igem2026 deployment layout).
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "scripts", "make_trajectory.py")

    env_py = os.environ.get("MD_PYTHON_BIN") or "/home/selp/.local/miniconda3/envs/igem2026/bin/python3"
    conda_bin = os.environ.get("MD_CONDA_BIN") or "/home/selp/.local/miniconda3/bin/conda"
    if os.path.exists(env_py):
        cmd = [env_py, script]
    elif os.path.exists(conda_bin):
        cmd = [conda_bin, "run", "-n", "igem2026", "python3", script]
    else:
        cmd = ["python3", script]

    cmd += [os.path.basename(local_task.rstrip("/")), "--local-dir", local_task]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "trajectory conversion timed out"}
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return {"ok": False, "error": (out or proc.stderr or "").strip()[-1000:]}
    try:
        return json.loads(out)
    except ValueError:
        return {"ok": False, "error": f"conversion produced non-JSON output: {out[-500:]}"}


def handle(ssh, cfg, args, local_task):
    if args.sub and args.sub != "sync":
        return {"ok": False, "error": f"unknown trajectory sub {args.sub!r}"}

    output_dir = os.path.join(local_task, "output")
    os.makedirs(output_dir, exist_ok=True)

    out_files = cfg.output_files()
    samples = _remote_samples(ssh, cfg)
    changed = _changed_files(ssh, cfg, samples, out_files, output_dir)

    if changed and not _stream_tar(ssh, cfg, changed, output_dir):
        return {"ok": False, "error": "output download failed"}

    replica_sizes = []
    for sample in samples:
        name = _remote_name(sample)
        total = 0
        for f in out_files:
            p = os.path.join(output_dir, name, f)
            if os.path.exists(p):
                total += os.path.getsize(p)
        replica_sizes.append(total)

    pdb_path = os.path.join(local_task, "cache", "trajectory", "topology.pdb")
    if changed or not os.path.exists(pdb_path):
        conv = _run_conversion(local_task)
        if not conv.get("ok"):
            return {"ok": False, "error": conv.get("error", "trajectory conversion failed")}
    else:
        conv = _existing_sizes(local_task)

    return {
        "ok": True,
        "pdbSize": conv.get("pdbSize", 0),
        "dcdSize": conv.get("dcdSize", 0),
        "dcdSizes": conv.get("dcdSizes", []),
        "previewSizes": conv.get("previewSizes", []),
        "previewFrames": conv.get("previewFrames", []),
        "samples": conv.get("samples", []),
        "replicaSizes": replica_sizes,
        "last100Sizes": conv.get("last100Sizes", []),
        "last100Frames": conv.get("last100Frames", []),
        "changed": len(changed),
    }
