"""File routes for magnetomech: remote file ops are not applicable to this
local computation task (no SSH host is contacted)."""


def handle(ssh, cfg, args, local_task):
    return {"ok": False, "error": "remote file operations are not applicable to magnetomech tasks"}