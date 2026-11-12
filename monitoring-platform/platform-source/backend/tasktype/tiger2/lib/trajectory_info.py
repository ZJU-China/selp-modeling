"""Remote trajectory file discovery + legacy PDB generation.

All task-specific file strings (topology names in input/, .dcd glob patterns,
the production dir resolved from the per-replica log symlink) are derived from
the task's TaskConfig so the shared tasktype never hardcodes them.
"""
import os, json

import re


def _job_sort_key(basename):
    """Sort key for DCD segments: explicit job<N> token wins, else mtime."""
    m = re.search(r"(?:^|[._-])job0*(\d+)(?:[._-]|$)", basename)
    if m:
        return (0, int(m.group(1)))
    return (1, 0)


def discover(ssh, cfg, num_replicas=None):
    remote_dir = cfg.remote_dir
    log_prefix = cfg.log_prefix
    num_replicas = int(num_replicas or cfg.num_replicas)
    input_dir = cfg.input_dir()

    parts = [f'echo "__PDB__" && (ls "{input_dir}/"*.pdb 2>/dev/null | head -1)']
    parts.append(f'echo "__PSF__" && (ls "{input_dir}/"*.psf 2>/dev/null | head -1)')
    for r in range(num_replicas):
        prod = f'$(dirname "$(readlink -f "{remote_dir}/logs/{r}/{log_prefix}.{r}.log" 2>/dev/null)" 2>/dev/null)'
        search = " ".join(f'"{d}"' for d in set(cfg.output_dirs(r) + cfg.production_dirs(r)))
        parts.append(
            f'echo "__DCD{r}__" && '
            f'(find {search} {prod} '
            f'-maxdepth 1 -type f -name "*.dcd" -printf "%T@\\t%f\\t%p\\n" 2>/dev/null || true)'
        )
    raw, _, _ = ssh.exec(" && ".join(parts), timeout=60)

    def extract(marker):
        idx = raw.find(marker)
        if idx == -1:
            return ""
        next_idx = -1
        for m in ("__PDB__", "__PSF__", "__DCD"):
            j = raw.find(m, idx + len(marker))
            if j != -1 and (next_idx == -1 or j < next_idx):
                next_idx = j
        return raw[idx + len(marker): next_idx if next_idx != -1 else None].strip()

    def parse_segments(block):
        """Dedupe by basename (newest wins) and order by job token."""
        by_name = {}
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            fields = line.split("\t")
            if len(fields) < 3:
                continue
            mtime, basename, path = fields[0], fields[1], "\t".join(fields[2:])
            prev = by_name.get(basename)
            if prev is None or mtime > prev[0]:
                by_name[basename] = (mtime, path)
        return [p for (_m, p) in sorted(
            by_name.values(), key=lambda e: _job_sort_key(os.path.basename(e[1]))
        )]

    result = {"pdb": extract("__PDB__") or None, "psf": extract("__PSF__") or None, "dcds": {}}
    for r in range(num_replicas):
        segs = parse_segments(extract(f"__DCD{r}__"))
        if segs:
            result["dcds"][str(r)] = segs
    return result

def gen_trajectory_pdb(ssh, cfg, output_path, replica=0, script_path=None):
    """Run the legacy trajectory-PDB generator on the remote, then download it."""
    script = script_path or os.path.expanduser("~/igem-2026/MD/gen_trajectory_pdb.py")
    out, err, code = ssh.exec(
        f"python3 {script} \"{cfg.remote_dir}\" \"{output_path}\" {replica}",
        timeout=600,
    )
    return {
        "ok": code == 0,
        "output_path": output_path,
        "output": (out or "")[-500:],
        "error": (err or "")[-500:] if code != 0 else None,
    }

def download_trajectory_pdb(ssh, remote_path, local_path):
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    return ssh.download(remote_path, local_path)
