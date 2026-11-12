"""Resolve how an external tool is invoked, shared by every task type.

Follows the convention already used by the generated drivers in
``scripts/cg_autopilot.py`` and the CG handoff artifacts::

    GROMACS_BIN="${GROMACS_BIN:-/opt/app/gromacs-2021.5/bin/gmx_mpi}"
    "$GROMACS_BIN" grompp -f em.mdp ...
    NAMD_BIN="${NAMD_BIN:-$HOME/NAMD_3.0.2_Linux-x86_64-netlrts-smp/namd3}"

so a tool is named by an environment variable that defaults to whatever the
deployment actually has. That covers both cases the platform needs:

  * on PATH -- configure the bare name, e.g. ``gmx``
  * not on PATH -- configure the absolute path, e.g. ``/opt/app/gromacs/bin/gmx_mpi``

GROMACS and MATLAB use this same code even though they live in different
places. MATLAB is the reason the configured value is a whole command line
rather than a single path: the iGEM server runs MATLAB from the
``mathworks/matlab`` image instead of installing it on the host, so the real
invocation is ``docker exec matlab-gui matlab``. Splitting on whitespace keeps
that expressible without a second config field.

Resolution order (per-task config wins over the ambient environment, because a
per-task value is a deliberate choice):

  1. ``tools.<name>`` in the task's own ``task_config.json``
  2. the environment (``GMX_BIN`` / ``GROMACS_BIN``, ``MATLAB_BIN``)
  3. the fallback, which is the bare name for tools that are on PATH
"""

from __future__ import annotations

import os
import shlex
import shutil

# Fallback per tool. Both are bare names on purpose: gmx is on PATH on the iGEM
# server (/usr/bin/gmx). The previously hardcoded /usr/local/gromacs/bin/gmx does
# not exist there, so CG energy analysis could not find GROMACS at all.
DEFAULTS = {
    "gmx": "gmx",
    "matlab": "matlab",
}

# Environment variables consulted for each tool, in order. GROMACS has been
# spelled both ways in this repo, so both are honoured.
ENV_VARS = {
    "gmx": ("GMX_BIN", "GROMACS_BIN"),
    "matlab": ("MATLAB_BIN",),
}


def resolve_argv(name: str, cfg: dict | None = None) -> list[str]:
    """The argv prefix used to invoke ``name``."""
    raw = None
    source = ""
    tools = (cfg or {}).get("tools")
    if isinstance(tools, dict):
        candidate = tools.get(name)
        if isinstance(candidate, str) and candidate.strip():
            raw, source = candidate.strip(), "task config"
    if raw is None:
        for var in ENV_VARS.get(name, ()):
            value = os.environ.get(var)
            if value and value.strip():
                raw, source = value.strip(), f"${var}"
                break
    if raw is None:
        raw, source = DEFAULTS.get(name, name), "default"

    try:
        argv = shlex.split(raw)
    except ValueError as e:
        raise ValueError(f"{name}: cannot parse the configured command {raw!r}: {e}") from e
    if not argv:
        raise ValueError(f"{name}: the configured command is empty")
    return argv


def executable(name: str, cfg: dict | None = None) -> str:
    """Just the binary, for callers that build their own argv."""
    return resolve_argv(name, cfg)[0]


def gmx_bin(cfg: dict | None = None) -> str:
    return executable("gmx", cfg)


def gmx_argv(cfg: dict | None = None) -> list[str]:
    return resolve_argv("gmx", cfg)


def matlab_argv(cfg: dict | None = None) -> list[str]:
    return resolve_argv("matlab", cfg)


# NAMD is the odd one out: it is not a single command but a build directory
# holding both ``charmrun`` and ``namd3``, and the two settings in this repo
# disagree about which half to name. ``process.namdBin`` names the directory,
# while the shell convention above names the binary (``$HOME/.../namd3``), so
# both are accepted and normalised to the directory.
NAMD_DIR_KEYS = ("namdBin", "namd_bin", "namdDir")
NAMD_FALLBACK_DIRS = (
    "~/software/NAMD_3.0.2_Linux-x86_64-netlrts-smp",
    "~/software/NAMD_3.0.2_Linux-x86_64-multicore",
    "~/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-netlrts-smp",
    "~/igem-2026/MD/NAMD_3.0.2_Linux-x86_64-multicore",
)


def namd_build_dir(cfg: dict | None = None, environ: dict | None = None) -> tuple[str, str]:
    """The configured NAMD build directory, and where the value came from."""
    cfg = cfg if isinstance(cfg, dict) else {}
    env = os.environ if environ is None else environ
    process = cfg.get("process")
    process = process if isinstance(process, dict) else {}
    tools = cfg.get("tools")
    tools = tools if isinstance(tools, dict) else {}
    from_process = next((process.get(k) for k in NAMD_DIR_KEYS if process.get(k)), None)

    raw: str | None = None
    source = ""
    for value, src in (
        (tools.get("namd3"), "task config tools.namd3"),
        (tools.get("namd"), "task config tools.namd"),
        (from_process, "task config process.namdBin"),
        (cfg.get("namdBin"), "task config namdBin"),
        (env.get("NAMD_BIN"), "$NAMD_BIN"),
    ):
        if isinstance(value, str) and value.strip():
            raw, source = value.strip(), src
            break
    if raw is None:
        return NAMD_FALLBACK_DIRS[0], "default"
    # A path ending in the binary names the binary; its parent is the build.
    if os.path.basename(raw) in ("namd3", "namd3.exe"):
        raw = os.path.dirname(raw)
    return raw, source


def describe_namd(cfg: dict | None = None) -> dict:
    """Describe the NAMD build the way a launch actually uses it.

    The local filesystem check is only indicative -- the launch happens over
    SSH on the compute server -- so this reports the configured location and
    whether it resolves *here*, and leaves the authoritative remote check to
    ``tiger2/lib/namd_control.resolve_namd_bin``.
    """
    raw, source = namd_build_dir(cfg)
    expanded = os.path.expanduser(raw)
    namd3 = os.path.join(expanded, "namd3")
    charmrun = os.path.join(expanded, "charmrun")
    exists = os.path.isfile(namd3) and os.access(namd3, os.X_OK)
    return {
        "name": "namd3",
        "ok": exists,
        "command": shlex.join([charmrun, namd3]),
        "argv": [charmrun, namd3],
        "buildDir": expanded,
        "source": source,
        "checkedLocally": True,
        **({} if exists else {
            "error": f"{namd3} is not executable on this host "
                     f"(the launch runs on the remote server, which is checked separately)"
        }),
    }


def describe(name: str, cfg: dict | None = None) -> dict:
    """A JSON-friendly description, for the Parameters panel and status output.

    Reports whether the resolved command actually resolves, so a stale path
    shows up in the UI instead of only as a failed run.
    """
    try:
        argv = resolve_argv(name, cfg)
    except ValueError as e:
        return {"name": name, "ok": False, "error": str(e)}

    head = argv[0]
    # A value containing a slash is a path: use it verbatim and report if it is
    # missing, because silently falling back would hide a typo.
    if "/" in head:
        found = os.path.exists(head)
        return {
            "name": name,
            "ok": found,
            "command": shlex.join(argv),
            "argv": argv,
            "viaContainer": os.path.basename(head) == "docker",
            **({} if found else {"error": f"{head} does not exist"}),
        }

    found_path = shutil.which(head)
    return {
        "name": name,
        "ok": bool(found_path),
        "command": shlex.join(argv),
        "argv": argv,
        "resolvedTo": found_path,
        "viaContainer": head == "docker",
        **({} if found_path else {"error": f"{head} is not on PATH"}),
    }


def describe_all(cfg: dict | None = None) -> dict:
    report = {name: describe(name, cfg) for name in DEFAULTS}
    # NAMD is reported alongside them so the panel shows every external tool a
    # task can launch, including the one used by the TIGER2 step.
    report["namd3"] = describe_namd(cfg)
    return report