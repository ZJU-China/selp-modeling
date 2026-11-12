"""Process scan for magnetomech tasks: nothing runs on a remote host."""


def handle(ssh, cfg, args, local_task):
    return {"ok": True, "processes": [], "jobs": [], "replicas": {}, "running": False}