"""Sim-status sync for magnetomech tasks: nothing to mirror from a remote
host, so the sync is a local no-op that never communicates."""


def handle(ssh, cfg, args, local_task):
    return {"ok": True, "samples": [], "changed": 0, "details": {}}