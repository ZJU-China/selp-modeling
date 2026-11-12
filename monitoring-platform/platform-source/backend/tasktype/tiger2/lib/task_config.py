"""Per-task configuration for the TIGER2 (NAMD) task type.

Extends BaseTaskConfig with NAMD-specific paths, process detection,
and directory management.  See lib/task_config_base.py for the shared logic.
"""
import json, os, re
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from _shared.task_config_base import BaseTaskConfig, merge, write_default as _write_default
from _shared.config_lookup import value_lookup

DEFAULT_REMOTE = {
    "tempDir": "{rd}/temp",
    "logPaths": [
        "{rd}/temp/logs/{r}/{lp}.{r}.log",
        "{rd}/logs/{r}/{lp}.{r}.log",
        "{rd}/temp/production/{r}/{lp}.{r}.log",
        "{rd}/production/{r}/{lp}.{r}.log",
        "{rd}/production_100ns_each/{r}/{lp}.{r}.log",
    ],
    "configPaths": [
        "{rd}/{lp}.conf",
        "{rd}/temp/{lp}.conf",
        "{rd}/config/{lp}.conf",
    ],
    "checkpointDirs": ["{rd}/output/{r}"],
    "outputDirs": ["{rd}/temp/output/{r}", "{rd}/output/{r}"],
    "analysisDir": "{rd}/analysis",
    "inputDir": "{rd}/input",
    "productionDirs": [
        "{rd}/temp/production/{r}",
        "{rd}/production/{r}",
        "{rd}/production_100ns_each/{r}",
    ],
}

DEFAULT_PROCESS = {
    "psPattern": "namd3.*{lp}|charmrun.*namd3",
    "pgrepPattern": "namd3 .*{lp}",
    # Left empty on purpose: an empty value lets namd_control discover the build
    # that is actually installed (see DEFAULT_NAMD_BIN_GLOBS) instead of
    # failing against a directory that may not exist. Set this to pin a build.
    "namdBin": "",
    "freshnessMinutes": 5,
}


def parse_output_root(conf_content):
    """Extract output_root pattern from a NAMD conf (TCL set output_root ...)."""
    for line in conf_content.splitlines():
        m = re.match(r'\s*set\s+output_root\s+"([^"]+)"', line)
        if m:
            return m.group(1)
    return None


class TaskConfig(BaseTaskConfig):
    """NAMD-specific task configuration."""

    def __init__(self, remote_dir, log_prefix, data=None, num_replicas=None,
                 steps_per_cycle=None, total_cycles=None):
        data = data or {}
        d = value_lookup(data)
        super().__init__(
            remote_dir=remote_dir,
            log_prefix=log_prefix or "tiger2",
            num_replicas=int(num_replicas or d.int_("numReplicas", 4)),
            steps_per_cycle=int(steps_per_cycle or d.int_("stepsPerCycle", 15000)),
            total_cycles=int(total_cycles or d.int_("totalCycles", 1667)),
            remote=merge(DEFAULT_REMOTE, data.get("remote")),
            process=merge(DEFAULT_PROCESS, data.get("process")),
            extra=data,
        )

    # -- NAMD-specific remote paths --
    def temp_dir(self):
        return self._fmt(self._remote["tempDir"])

    def log_paths(self, r):
        return [self._fmt(t, r) for t in self._remote["logPaths"]]

    def log_dirs(self, r):
        return sorted({os.path.dirname(p) for p in self.log_paths(r)})

    def config_paths(self):
        return [self._fmt(t) for t in self._remote["configPaths"]]

    def checkpoint_dirs(self, r):
        return [self._fmt(t, r) for t in self._remote["checkpointDirs"]]

    def output_dirs(self, r):
        return [self._fmt(t, r) for t in self._remote["outputDirs"]]

    def production_dirs(self, r):
        return [self._fmt(t, r) for t in self._remote["productionDirs"]]

    def analysis_dir(self):
        return self._fmt(self._remote["analysisDir"])

    def input_dir(self):
        return self._fmt(self._remote["inputDir"])

    def prepare_dirs(self, ssh):
        """Create all necessary remote directories before NAMD starts."""
        temp = self.temp_dir()
        reps = list(range(self.num_replicas))
        dirs = [f"{temp}/logs/{r}" for r in reps]
        dirs += [f"{temp}/output/{r}" for r in reps]

        conf_content = None
        for cp in self.config_paths():
            out, _, _ = ssh.exec(f"cat {cp} 2>/dev/null")
            if out.strip():
                conf_content = out
                break
        if conf_content:
            output_root = parse_output_root(conf_content)
            if output_root:
                for r in reps:
                    d = os.path.join(temp, output_root.replace("%s", str(r)))
                    dirs.append(d)

        if dirs:
            mkdirs = " ".join(dirs)
            ssh.exec(f"mkdir -p {mkdirs}")
        return dirs

    # -- NAMD process detection --
    def ps_pattern(self):
        return self._fmt(self._process["psPattern"])

    def pgrep_pattern(self):
        return self._fmt(self._process["pgrepPattern"])

    def namd_bin(self):
        return self._process.get("namdBin")

    def env_setup(self):
        return (self._process.get("envSetup") or "").strip()

    # -- convergence --
    def convergence_metrics(self):
        return self.extra.get("convergence", {}).get("metrics")

    def convergence(self):
        return self.extra.get("convergence", {})

    def slurm_job_id(self):
        return self.extra.get("monitor", {}).get("slurmJobId")


# Keep module-level names for backward compatibility
_merge = merge

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "task_config.template.json")


def load(path, remote_dir=None, log_prefix=None, **cli_overrides):
    data = None
    if path:
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = None
    if not remote_dir and data:
        remote_dir = data.get("remoteDir")
    if not log_prefix and data:
        log_prefix = data.get("logPrefix")
    return TaskConfig(
        remote_dir, log_prefix, data,
        num_replicas=cli_overrides.get("num_replicas"),
        steps_per_cycle=cli_overrides.get("steps_per_cycle"),
        total_cycles=cli_overrides.get("total_cycles"),
    )


def write_default(path, remote_dir=None, log_prefix=None):
    return _write_default(
        path, TEMPLATE_PATH, DEFAULT_PROCESS,
        defaults_replicas=4, defaults_steps=15000, defaults_cycles=1667,
        remote_dir=remote_dir, log_prefix=log_prefix,
    )
