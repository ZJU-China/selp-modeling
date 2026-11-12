"""Sim-status data sync (moved from backend/services/sim-status-sync.js).

Downloads every sample's GROMACS md.log (and its mdp) to the task's local
logs/<sample_name>/ dir so the backend's gen_sim_status.py can analyse them
offline.

The sync is incremental: one remote command stats every candidate file, and
only files that are missing locally or newer than the local copy are fetched
(one bulk loop per chunk, files separated by "###<path>" markers). A completed
batch therefore costs two tiny SSH round trips per cycle instead of a full
re-download. Candidate paths come from the task's TaskConfig (sampleGlobs +
mdlogName/mdpName). The optional batch-level mdp is fetched into logs/_batch/
as a fallback for nsteps/dt defaults.
"""
import os

MARK = "###"


def _remote_name(path):
    return path.rstrip("/").split("/")[-1]


def _remote_samples(ssh, cfg):
    samples = []
    for pattern in cfg.sample_globs():
        out, _, _ = ssh.exec(f'ls -d {pattern} 2>/dev/null || true', timeout=30)
        for line in out.splitlines():
            line = line.strip()
            if line:
                samples.append(line)
    return samples


def _candidates(sample, mdlog_name, mdp_name):
    """Candidate file paths for a sample: the known md.log name, common
    fallbacks, the named mdp, and any mdp in the sample dir."""
    return [
        f'{sample}/{mdlog_name}',
        f'{sample}/md.log',
        f'{sample}/gromacs.log',
        f'{sample}/{mdp_name}',
        f'{sample}/*.mdp',
    ]


def _stat_command(candidates):
    """One remote command printing '<mtime> <path>' per existing candidate."""
    parts = []
    for c in candidates:
        parts.append(f'for f in {c}; do [ -f "$f" ] && stat -c "%Y %n" "$f"; done')
    return "\n".join(parts)


def _changed_files(ssh, candidates, logs_dir):
    """Return {remote_path: local_path} for files newer than local (or missing)."""
    out, _, _ = ssh.exec(_stat_command(candidates), timeout=60)
    changed = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or " " not in line:
            continue
        mtime_s, path = line.split(" ", 1)
        if not mtime_s.isdigit():
            continue
        name = _remote_name(os.path.dirname(path))
        local = os.path.join(logs_dir, name, os.path.basename(path))
        try:
            local_mtime = os.path.getmtime(local)
        except OSError:
            local_mtime = -1
        if int(mtime_s) > local_mtime:
            changed[path] = local
    return changed


def _fetch_command(paths):
    """One remote loop catting the given paths, '###<path>' separated."""
    lines = []
    for p in paths:
        lines.append(f'echo "{MARK}{p}" && cat "{p}" 2>/dev/null || true')
    return "\n".join(lines)


def handle(ssh, cfg, args, local_task):
    if args.sub and args.sub != "sync":
        return {"ok": False, "error": f"unknown status sub {args.sub!r}"}

    logs_dir = os.path.join(local_task, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    mdlog_name = cfg.mdlog_name()
    mdp_name = cfg.mdp_name()

    # Batch-level mdp (shared across samples) -> logs/_batch/
    batch_dir = os.path.join(logs_dir, "_batch")
    batch_mdp_fetched = False
    batch_mdp = cfg.batch_mdp()
    if batch_mdp:
        batch_local = os.path.join(batch_dir, os.path.basename(batch_mdp))
        try:
            fresh = os.path.getmtime(batch_local)
        except OSError:
            fresh = -1
        out, _, _ = ssh.exec(f'stat -c "%Y %n" "{batch_mdp}" 2>/dev/null || true', timeout=30)
        if out.strip():
            mtime_s = out.split()[0]
            if mtime_s.isdigit() and int(mtime_s) > fresh:
                out2, _, _ = ssh.exec(f'cat "{batch_mdp}" 2>/dev/null', timeout=30)
                if out2.strip():
                    os.makedirs(batch_dir, exist_ok=True)
                    with open(batch_local, "w") as f:
                        f.write(out2)
            batch_mdp_fetched = True

    samples = _remote_samples(ssh, cfg)
    details = {}

    for sample in samples:
        name = _remote_name(sample)
        details[name] = {"dir": sample, "files": {}}

    # Stat all candidates in one shot, then fetch only changed files.
    candidates = []
    for sample in samples:
        candidates.extend(_candidates(sample, mdlog_name, mdp_name))
    changed = _changed_files(ssh, candidates, logs_dir)

    paths = list(changed)
    for chunk in [paths[i:i + 25] for i in range(0, max(len(paths), 1), 25)]:
        out, _, _ = ssh.exec(_fetch_command(chunk), timeout=90)
        current_path = None
        buffer = []
        for line in out.splitlines():
            if line.startswith(MARK):
                if current_path and buffer:
                    _write_file(changed[current_path], "\n".join(buffer))
                    buffer = []
                current_path = line[len(MARK):]
            else:
                buffer.append(line)
        if current_path and buffer:
            _write_file(changed[current_path], "\n".join(buffer))

    for remote_path, local in changed.items():
        name = _remote_name(os.path.dirname(remote_path))
        if os.path.exists(local):
            details[name]["files"][os.path.basename(remote_path)] = os.path.getsize(local)

    return {
        "ok": True,
        "samples": [name for name in details if details[name]["files"]],
        "batch_mdp": batch_mdp_fetched,
        "changed": len(changed),
        "details": details,
    }


def _write_file(local_path, content):
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "w") as f:
        f.write(content)
