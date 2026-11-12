"""Shell route for magnetomech: arbitrary remote commands are not applicable
to this local computation task."""


def handle(ssh, cfg, args, local_task):
    return {"ok": False, "error": "shell is not applicable to magnetomech tasks"}