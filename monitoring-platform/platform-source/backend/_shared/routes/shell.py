"""Shared route: arbitrary remote command execution."""


def handle(ssh, cfg, args, local_task):
    if not args.cmd:
        return {"ok": False, "error": "command required"}
    timeout = int(args.timeout or 30)
    out, err, code = ssh.exec(args.cmd, timeout=timeout)
    return {
        "ok": code == 0,
        "exitCode": code,
        "stdout": (out or "")[-50000:],
        "stderr": (err or "")[:5000],
        "command": args.cmd,
    }
