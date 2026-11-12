"""Shared route handlers for remote file operations."""
import base64


def _q(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def _parse_listing(raw):
    items = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        perms = parts[0]
        try:
            size = int(parts[4])
        except ValueError:
            size = 0
        date = " ".join(parts[5:7])
        name = " ".join(parts[7:])
        if not name or name in (".", ".."):
            continue
        items.append({
            "name": name,
            "isDir": perms.startswith("d"),
            "size": size,
            "modified": date,
            "permissions": perms,
        })
    return items


def handle(ssh, cfg, args, local_task):
    sub = args.sub
    if sub == "list":
        target = args.path or "."
        out, _, _ = ssh.exec(
            f"ls -la --time-style=long-iso {_q(target)} 2>/dev/null | tail -n +2", timeout=10
        )
        return {"ok": True, "path": target, "items": _parse_listing(out)}

    if sub == "read":
        if not args.path:
            return {"ok": False, "error": "path required"}
        out, _, _ = ssh.exec(f"cat {_q(args.path)} 2>/dev/null", timeout=15)
        return {"ok": True, "content": out, "path": args.path}

    if sub == "write":
        if not args.path or args.content is None:
            return {"ok": False, "error": "path and content required"}
        b64 = base64.b64encode(str(args.content).encode("utf-8")).decode()
        _, _, code = ssh.exec(f"echo {b64} | base64 -d > {_q(args.path)}", timeout=30)
        return {"ok": code == 0, "path": args.path}

    if sub == "delete":
        if not args.path:
            return {"ok": False, "error": "path required"}
        ssh.exec(f"rm -f {_q(args.path)}", timeout=10)
        return {"ok": True}

    if sub == "mkdir":
        if not args.path:
            return {"ok": False, "error": "path required"}
        ssh.exec(f"mkdir -p {_q(args.path)}", timeout=10)
        return {"ok": True}

    return {"ok": False, "error": f"unknown files sub {sub!r}"}
