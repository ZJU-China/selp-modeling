"""Read one task setting no matter where it was written.

Every task type ships a ``task_config.template.json`` that nests its run
settings under ``defaults`` / ``process`` / ``remote``, because that is what the
tasktype's own Python reads. The Flow Console's parameter panel, on the other
hand, writes the values it collects as *flat* top-level keys into the same
file (``persistTaskConfig`` is a plain merge).

Those two shapes have to agree, or a parameter the user set in the UI is
silently discarded and the run uses the template default instead. Rather than
require one side to move -- which would break every hand-authored config and
every older task already on disk -- the readers look in both places:

    CLI flag  >  top-level key  >  defaults.<key>

Top level wins over ``defaults`` because it is the value a person or the panel
most recently set; ``defaults`` is the shipped fallback. CLI stays on top
because that is an explicit override for one invocation.
"""

from __future__ import annotations

from typing import Any


class ValueLookup:
    """Flat-first, nested-fallback reader over one task_config.json."""

    # Keys under `defaults` that hold values rather than a nested group.
    GROUPS = ("remote", "process", "monitor", "trajectory", "convergence")

    def __init__(self, data: Any):
        self.data = data if isinstance(data, dict) else {}
        defaults = self.data.get("defaults")
        self.defaults = defaults if isinstance(defaults, dict) else {}

    def raw(self, key: str, fallback: Any = None) -> Any:
        """The configured value for ``key``, or ``fallback`` when unset."""
        if key in self.data and self.data[key] not in (None, ""):
            return self.data[key]
        if key in self.defaults and self.defaults[key] not in (None, ""):
            return self.defaults[key]
        return fallback

    def int_(self, key: str, fallback: int) -> int:
        try:
            return int(float(self.raw(key)))
        except (TypeError, ValueError):
            return int(fallback)

    def float_(self, key: str, fallback: float) -> float:
        try:
            return float(self.raw(key))
        except (TypeError, ValueError):
            return float(fallback)

    def str_(self, key: str, fallback: str = "") -> str:
        value = self.raw(key)
        if value is None:
            return fallback
        text = str(value).strip()
        return text or fallback


def value_lookup(data: Any) -> ValueLookup:
    return ValueLookup(data)