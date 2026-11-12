"""Base TaskConfig with shared logic for all MD engine tasktypes.

Provides _merge(), _fmt(), load(), write_default() and the common fields
(remote_dir, log_prefix, num_replicas, steps_per_cycle, total_cycles,
ps_pattern, pgrep_pattern, freshness_minutes). Engine-specific subclasses
(NAMD, GROMACS) add their own path helpers and configuration accessors.
"""
import json, os


def merge(defaults, override):
    """Deep-merge override into defaults (override wins)."""
    if not isinstance(override, dict):
        return defaults
    merged = dict(defaults)
    for k, v in override.items():
        merged[k] = merge(defaults[k], v) if isinstance(defaults.get(k), dict) else v
    return merged


class BaseTaskConfig:
    """Shared configuration fields for all MD engine tasktypes."""

    def __init__(self, remote_dir, log_prefix, num_replicas=1,
                 steps_per_cycle=500000, total_cycles=10,
                 remote=None, process=None, extra=None):
        self.remote_dir = (remote_dir or "").rstrip("/")
        self.log_prefix = log_prefix or ""
        self.num_replicas = int(num_replicas)
        self.steps_per_cycle = int(steps_per_cycle)
        self.total_cycles = int(total_cycles)
        self._remote = remote or {}
        self._process = process or {}
        self.extra = extra or {}

    def _fmt(self, template, r=None):
        return template.format(
            rd=self.remote_dir, lp=self.log_prefix,
            r="" if r is None else int(r),
        )

    def ps_pattern(self):
        return self._process.get("psPattern", "")

    def pgrep_pattern(self):
        return self._process.get("pgrepPattern", "")

    def freshness_minutes(self):
        return int(self._process.get("freshnessMinutes", 5))


def load_base(raw, defaults_remote, defaults_process, cli_overrides=None):
    """Common load helper: merge raw config with engine-specific defaults."""
    cli = cli_overrides or {}
    remote = merge(defaults_remote, raw.get("remote", {}))
    process = merge(defaults_process, raw.get("process", {}))
    defaults = raw.get("defaults", {})

    def _f(value, fallback):
        try:
            return float(value) if value not in (None, "") else float(fallback)
        except (TypeError, ValueError):
            return float(fallback)

    def _i(value, fallback):
        return int(_f(value, fallback))

    return remote, process, defaults, cli, _f, _i


def write_default(path, template_path, defaults_process, defaults_replicas,
                  defaults_steps, defaults_cycles, remote_dir=None, log_prefix=None):
    """Write a new task's task_config.json from the engine's default template."""
    if os.path.exists(path):
        return path
    try:
        with open(template_path) as f:
            cfg = json.load(f)
        cfg.pop("_comment", None)
    except (OSError, ValueError):
        cfg = {
            "process": defaults_process,
            "defaults": {
                "numReplicas": defaults_replicas,
                "stepsPerCycle": defaults_steps,
                "totalCycles": defaults_cycles,
            },
        }
    if remote_dir:
        cfg["remoteDir"] = remote_dir
    if log_prefix:
        cfg["logPrefix"] = log_prefix
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    return path
