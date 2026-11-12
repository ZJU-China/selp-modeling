"""Report how each shared external tool resolves for one task.

Called by the backend (services/task-execution.js) so the Flow Console can show
the real invocation instead of a user guessing at paths. The resolution rules
live in tools.py; this is only the entry point that reads one task's config and
prints a JSON report.

    python3 tools_probe.py <path to task_config.json>
"""
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from _shared.tools import describe_all  # noqa: E402


def main() -> int:
    cfg = {}
    if len(sys.argv) > 1 and sys.argv[1]:
        try:
            with open(sys.argv[1]) as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                cfg = loaded
        except (OSError, ValueError):
            # A missing or unreadable config is not fatal: the tools still
            # resolve from the environment / defaults, which is worth showing.
            cfg = {}

    report = describe_all(cfg)
    # hostname tells the panel which host the PATH was resolved on, so a task
    # showing gmx -> /usr/bin/gmx is unambiguous about where that came from.
    import socket
    report["_host"] = socket.gethostname()
    json.dump(report, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())