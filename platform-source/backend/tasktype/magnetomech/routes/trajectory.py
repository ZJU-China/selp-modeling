"""Trajectory route for magnetomech: no molecular trajectory exists."""


def handle(ssh, cfg, args, local_task):
    return {"ok": True, "frames": [], "status": "none"}