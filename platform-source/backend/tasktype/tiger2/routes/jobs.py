"""Process + replica step scan (moved from backend/routes/tasks.js and sync.js)."""
import re


def handle(ssh, cfg, args, local_task):
    ps_raw, _, _ = ssh.exec(
        f'ps aux | grep -E "{cfg.ps_pattern()}" | grep -v grep || true', timeout=10
    )
    processes = []
    for line in ps_raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 11:
            continue
        pid = parts[1]
        try:
            pid = int(pid)
        except ValueError:
            continue
        cmd = line[line.index(parts[10]):]
        m = re.search(r"(\S+\.conf)", cmd)
        processes.append({"pid": pid, "command": cmd, "config": m.group(1) if m else None})

    replicas = {}
    for ri in range(cfg.num_replicas):
        out, _, _ = ssh.exec(
            f'tail -5 "{cfg.log_paths(ri)[1]}" 2>/dev/null | grep -oP \'ENERGY:\\s+\\K\\d+\' | tail -1 || echo 0',
            timeout=10,
        )
        try:
            s = int(out.strip())
        except ValueError:
            s = 0
        if s > 0:
            replicas[str(ri)] = {"step": s, "logPath": f"logs/{ri}/{cfg.log_prefix}.{ri}.log"}

    return {"ok": True, "processes": processes, "replicas": replicas}
