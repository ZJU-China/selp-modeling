"""Sim-status data sync (moved from backend/services/sim-status-sync.js).

Downloads every per-replica log (fresh run + resumed jobs share a log stem,
e.g. tiger2_snoopytag.{r}.log and tiger2_snoopytag_resume725.{r}.log) and the
task config to the local task dir so the backend's gen_sim_status.py can
analyse them and the DCD merger can compute segment base steps. Candidate paths
come from the task's TaskConfig (logPaths / configPaths).
"""
import os, re


def _fetch_first(ssh, paths):
    for p in paths:
        out, _, code = ssh.exec(f"cat {p} 2>/dev/null")
        if code == 0 and out.strip():
            return out
    return None


def _log_stem(log_prefix):
    """Strip the _resumeN suffix so all segments of a run match the glob."""
    return re.sub(r"_resume\d*$", "", log_prefix) or log_prefix


def handle(ssh, cfg, args, local_task):
    if args.sub and args.sub != "sync":
        return {"ok": False, "error": f"unknown status sub {args.sub!r}"}

    logs_dir = os.path.join(local_task, "logs")
    results = {}
    stem = _log_stem(cfg.log_prefix)
    for r in range(cfg.num_replicas):
        dirs = cfg.log_dirs(r)
        if not dirs:
            results[str(r)] = {}
            continue
        search = " ".join(f'"{d}"' for d in dirs)
        raw, _, _ = ssh.exec(
            f'find {search} -maxdepth 1 -type f -name "{stem}*.{r}.log" '
            f'-printf "%T@\\t%f\\t%p\\n" 2>/dev/null',
            timeout=60,
        )
        by_name = {}
        for line in raw.splitlines():
            fields = line.split("\t")
            if len(fields) < 3:
                continue
            mtime, base, path = fields[0], fields[1], "\t".join(fields[2:])
            prev = by_name.get(base)
            if prev is None or mtime > prev[0]:
                by_name[base] = (mtime, path)
        fetched = {}
        for _mtime, path in sorted(by_name.values()):
            content, _, code = ssh.exec(f"cat {path} 2>/dev/null", timeout=60)
            if code == 0 and content.strip():
                fetched[os.path.basename(path)] = content
        if fetched:
            d = os.path.join(logs_dir, str(r))
            os.makedirs(d, exist_ok=True)
            for base, content in fetched.items():
                with open(os.path.join(d, base), "w") as f:
                    f.write(content)
            results[str(r)] = {base: len(content) for base, content in fetched.items()}
        else:
            results[str(r)] = {}

    config_ok = False
    conf = _fetch_first(ssh, cfg.config_paths())
    if conf:
        conf_dir = os.path.join(local_task, "config")
        os.makedirs(conf_dir, exist_ok=True)
        with open(os.path.join(conf_dir, f"{cfg.log_prefix}.conf"), "w") as f:
            f.write(conf)
        config_ok = True

    return {"ok": True, "logs": results, "config": config_ok}
