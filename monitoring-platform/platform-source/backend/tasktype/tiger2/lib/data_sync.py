"""Data synchronization between local and remote server.

Remote paths are derived from the task's TaskConfig (temp/ layout, log and
output locations).
"""
import os, json

def upload_input(ssh, cfg, local_input_dir):
    """Upload input files (PDB, PSF, toppar) to remote temp/.

    Flow links (input/flow-<prevId> symlinks) point at a sibling task's local
    output dir and must never be shipped to the remote host; they are skipped.
    """
    remote_temp_dir = cfg.temp_dir()
    if not os.path.isdir(local_input_dir):
        return {"ok": False, "error": f"Local input dir not found: {local_input_dir}"}

    ssh.exec(f"mkdir -p {remote_temp_dir}/input")
    files = []
    for name in os.listdir(local_input_dir):
        if name.startswith("flow-"):
            continue
        local_path = os.path.join(local_input_dir, name)
        remote_path = f"{remote_temp_dir}/input/{name}"
        if os.path.isdir(local_path):
            if not ssh.upload(local_path, remote_path):
                return {"ok": False, "error": f"Upload failed: {name}"}
        else:
            if not ssh.upload(local_path, remote_path):
                return {"ok": False, "error": f"Upload failed: {name}"}
        files.append(name)
    return {"ok": True, "files": files}

def upload_config(ssh, cfg, local_config_dir):
    """Upload config files to remote temp/."""
    remote_temp_dir = cfg.temp_dir()
    if not os.path.isdir(local_config_dir):
        return {"ok": False, "error": "No config dir"}
    for f in os.listdir(local_config_dir):
        if f.endswith(".conf") or f.endswith(".namd"):
            local_path = os.path.join(local_config_dir, f)
            remote_path = os.path.join(remote_temp_dir, f)
            ssh.upload(local_path, remote_path)
    return {"ok": True}

def download_logs(ssh, cfg, local_logs_dir):
    """Download NAMD log files from remote to local logs/."""
    os.makedirs(local_logs_dir, exist_ok=True)
    results = {}
    for r in range(int(cfg.num_replicas)):
        rep_dir = os.path.join(local_logs_dir, str(r))
        os.makedirs(rep_dir, exist_ok=True)
        remote_log = cfg.log_paths(r)[0]
        local_log = os.path.join(rep_dir, f"{cfg.log_prefix}.{r}.log")
        ok = ssh.download(remote_log, local_log)
        results[str(r)] = ok
        if ok:
            try:
                size = os.path.getsize(local_log)
                results[str(r)] = size
            except:
                pass
    return results

def download_output(ssh, cfg, local_output_dir):
    """Download DCD/restart files from remote to local output/."""
    os.makedirs(local_output_dir, exist_ok=True)
    results = {}
    for r in range(int(cfg.num_replicas)):
        rep_dir = os.path.join(local_output_dir, str(r))
        os.makedirs(rep_dir, exist_ok=True)
        remote_rep = cfg.output_dirs(r)[0]
        ok = ssh.download(remote_rep + "/.", rep_dir + "/")
        results[str(r)] = ok
    return results

def sync_all(ssh, cfg, local_task_dir):
    """Full sync: download logs and output from remote."""
    remote_temp_dir = cfg.temp_dir()
    logs_dir = os.path.join(local_task_dir, "logs")
    output_dir = os.path.join(local_task_dir, "output")

    reps = ",".join(str(i) for i in range(int(cfg.num_replicas)))
    ssh.exec(f"mkdir -p {remote_temp_dir}/logs/{{{reps}}} {remote_temp_dir}/output/{{{reps}}}")

    logs = download_logs(ssh, cfg, logs_dir)
    dcds = download_output(ssh, cfg, output_dir)

    # Collect DCD sizes
    dcd_sizes = {}
    for r in range(int(cfg.num_replicas)):
        rep_dir = os.path.join(output_dir, str(r))
        if os.path.isdir(rep_dir):
            dcds_found = [f for f in os.listdir(rep_dir) if f.endswith(".dcd")]
            dcd_sizes[str(r)] = {
                "count": len(dcds_found),
                "files": dcds_found[-3:] if dcds_found else [],
            }

    return {
        "logs": logs,
        "output": dcd_sizes,
    }

def organize(ssh, cfg, local_task_dir):
    """Organize remote temp/ output into structured dirs, then sync."""
    remote_temp_dir = cfg.temp_dir()
    reps = " ".join(str(i) for i in range(int(cfg.num_replicas)))
    # Use existing organize logic via SSH
    out, err, code = ssh.exec(f"""
        src="{remote_temp_dir}/production"
        if [ -d "$src" ]; then
            for r in {reps}; do
                [ -d "$src/$r" ] || continue
                mkdir -p "{remote_temp_dir}/logs/$r" "{remote_temp_dir}/output/$r"
                for f in "$src/$r/"*.log; do
                    [ -f "$f" ] && mv "$f" "{remote_temp_dir}/logs/$r/"
                done
                for f in "$src/$r/"*; do
                    [ -f "$f" ] && mv "$f" "{remote_temp_dir}/output/$r/"
                done
                rmdir "$src/$r" 2>/dev/null || true
            done
            rmdir "$src" 2>/dev/null || true
        fi
        echo DONE
    """)
    if code != 0:
        return {"ok": False, "error": err}
    # Then sync
    result = sync_all(ssh, cfg, local_task_dir)
    result["ok"] = True  # type: ignore
    return result
