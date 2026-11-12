"""Process + SLURM job scan (moved from backend/routes/tasks.js and sync.js).

Deliberately light: it runs every 8s from the backend sync loop, so it only
does the two SSH calls needed to detect gmx processes and SLURM jobs. Per-
sample step/progress is not scanned here; the authoritative numbers come from
gen_sim_status.py after the (bulk) route-status log sync.
"""
from lib import gmx


def handle(ssh, cfg, args, local_task):
    processes = gmx.gmx_processes(ssh, cfg)
    jobs = gmx.slurm_jobs(ssh, cfg)

    running = bool(processes) or any(
        j["state"] in ("RUNNING", "PENDING", "COMPLETING", "CONFIGURING", "SUSPENDED")
        for j in jobs
    )
    return {"ok": True, "processes": processes, "jobs": jobs, "replicas": {}, "running": running}
