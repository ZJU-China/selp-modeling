"""Per-task configuration for the magnetomech (CG-modulus -> field deformation)
task type.

Extends BaseTaskConfig; the meaningful fields are the "magnetomech", "particle"
and "field" sections, which are read back verbatim by main.py and handed to
code/magnetomech/compute.run.
"""
import json, os
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from _shared.task_config_base import BaseTaskConfig, merge, write_default as _write_default


DEFAULT_PROCESS = {
    "psPattern": "magnetomech",
    "pgrepPattern": "magnetomech",
    "freshnessMinutes": 5,
}


class TaskConfig(BaseTaskConfig):
    def __init__(self, remote_dir, log_prefix, extra):
        super().__init__(remote_dir=remote_dir, log_prefix=log_prefix,
                         num_replicas=1, steps_per_cycle=500000, total_cycles=1,
                         remote={}, process=DEFAULT_PROCESS, extra=extra)

    def magnetomech_params(self):
        section = self.extra.get("magnetomech") or {}
        return {
            "modulusMode": section.get("modulusMode") or "affine",
            "modulusKpa": section.get("modulusKpa"),
            "modulusPath": section.get("modulusPath"),
        }

    def particle_params(self):
        return (self.extra.get("particle") or {}).copy()

    def field_params(self):
        return (self.extra.get("field") or {}).copy()

    def magnetomech_fields(self):
        return {
            "temperatureK": self.extra.get("temperatureK", 310.0),
            "coupling": self.extra.get("coupling", 0.25),
            "demagFactor": self.extra.get("demagFactor", 1.0 / 3.0),
        }


TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "task_config.template.json")


def load(raw, cli_overrides=None):
    cli = cli_overrides or {}
    process = merge(DEFAULT_PROCESS, raw.get("process", {}))
    return TaskConfig(
        remote_dir=cli.get("remote_dir") or raw.get("remoteDir") or "",
        log_prefix=cli.get("log_prefix") or raw.get("logPrefix") or "magnetomech",
        extra=raw,
    )


def load_config(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return load(raw)


def load_raw(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_default(path, remote_dir=None, log_prefix=None):
    return _write_default(
        path, TEMPLATE_PATH, DEFAULT_PROCESS,
        defaults_replicas=1, defaults_steps=500000, defaults_cycles=1,
        remote_dir=remote_dir, log_prefix=log_prefix,
    )