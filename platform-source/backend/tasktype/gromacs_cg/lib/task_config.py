"""Per-task configuration for the GROMACS (CG) task type.

Extends BaseTaskConfig with GROMACS-specific paths, SLURM settings,
and sample detection.  See lib/task_config_base.py for the shared logic.
"""
import json, os
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from _shared.task_config_base import BaseTaskConfig, merge, write_default as _write_default
from _shared.config_lookup import value_lookup

DEFAULT_REMOTE = {
    "logPaths": [
        "{rd}/{s}/{lp}",
        "{rd}/{s}/md.log",
        "{rd}/{s}/gromacs.log",
    ],
    "mdpPaths": [
        "{rd}/{s}/{mp}",
        "{rd}/{s}/md_out.mdp",
        "{rd}/{s}/gromacs_out.mdp",
    ],
}

DEFAULT_PROCESS = {
    "psPattern": "gmx_mpi mdrun|gmx mdrun|mdrun_mpi",
    "pgrepPattern": "gmx.*mdrun",
    "freshnessMinutes": 5,
}


class TaskConfig(BaseTaskConfig):
    """GROMACS-specific task configuration."""

    def __init__(self, remote_dir, log_prefix, num_replicas, steps_per_cycle,
                 total_cycles, protein, remote, process, extra):
        super().__init__(
            remote_dir=remote_dir,
            log_prefix=log_prefix,
            num_replicas=num_replicas,
            steps_per_cycle=steps_per_cycle,
            total_cycles=total_cycles,
            remote=remote,
            process=process,
            extra=extra,
        )
        self.protein = protein

    # -- GROMACS remote paths --
    def log_paths(self, sample):
        return [p.format(rd=self.remote_dir, lp=self.log_prefix, s=sample)
                for p in self._remote["logPaths"]]

    def mdp_paths(self, sample):
        mp = self.mdp_name()
        return [p.format(rd=self.remote_dir, lp=self.log_prefix, s=sample, mp=mp)
                for p in self._remote["mdpPaths"]]

    # -- GROMACS config accessors --
    def mdlog_name(self):
        return (self.extra.get("gromacs") or {}).get("mdlogName", "relax.log")

    def mdp_name(self):
        return (self.extra.get("gromacs") or {}).get("mdpName", "relax_out.mdp")

    def batch_mdp(self):
        return (self.extra.get("gromacs") or {}).get("batchMdp")

    def planned_ns(self):
        v = (self.extra.get("gromacs") or {}).get("plannedNs")
        try:
            if v is not None:
                return float(v)
        except (TypeError, ValueError):
            pass
        return self.total_cycles

    def output_files(self):
        return ((self.extra.get("gromacs") or {}).get("outputFiles")
                or ["relax.xtc", "relax.gro", "deformed.gro", "relax.tpr",
                    "relax.edr", "relax.cpt"])

    def sample_globs(self):
        rd = self.remote_dir
        raw = (self.extra.get("gromacs") or {}).get("sampleGlobs", ["*"])
        out = []
        for g in raw:
            if g.startswith("/"):
                out.append(g.format(rd=rd))
            else:
                out.append(os.path.join(rd, g).format(rd=rd))
        return out

    # -- SLURM --
    def slurm_user(self):
        return (self.extra.get("slurm") or {}).get("user")

    def slurm_account(self):
        return (self.extra.get("slurm") or {}).get("account")

    def slurm_job_prefix(self):
        return (self.extra.get("slurm") or {}).get("jobPrefix")

    def slurm_partition(self):
        return (self.extra.get("slurm") or {}).get("partition")

    # -- launch --
    def gmx_bin(self):
        """The gmx command, or None to use the shared resolver."""
        return (self.extra.get("gromacs") or {}).get("gmxBin")

    def run_subdir(self):
        """Subdirectory of remoteDir holding each sample's inputs."""
        return (self.extra.get("gromacs") or {}).get("runSubdir") or ""

    def init_gro(self):
        """Starting coordinates for grompp."""
        return (self.extra.get("gromacs") or {}).get("initGro") or "init.gro"

    def topology(self):
        """System topology, if the task names one."""
        return (self.extra.get("gromacs") or {}).get("topology")

    def ntomp(self):
        """OpenMP threads per gmx process; 0 means "let GROMACS decide"."""
        try:
            return int((self.extra.get("gromacs") or {}).get("ntomp") or 0)
        except (TypeError, ValueError):
            return 0

    def smoke_steps(self):
        """Step override for a smoke run, or None for the configured length."""
        v = (self.extra.get("gromacs") or {}).get("smokeSteps")
        try:
            return int(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    def defffnm(self):
        """Base name for GROMACS output files (deffnm)."""
        return (self.extra.get("gromacs") or {}).get("deffnm") or self.log_prefix

    # -- defaults/metadata --
    def timestep_fs(self):
        v = (self.extra.get("defaults") or {}).get("timestepFs", 20)
        try:
            return float(v)
        except (TypeError, ValueError):
            return 20.0

    def force_field(self):
        return (self.extra.get("defaults") or {}).get("forceField", "Martini 3.0.0")

    def solvent(self):
        return (self.extra.get("defaults") or {}).get("solvent", "CG water + ions")

    def hmr_mass(self):
        v = (self.extra.get("defaults") or {}).get("hmrMass", 0)
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    def temp_min(self):
        v = (self.extra.get("defaults") or {}).get("tempMin", 310)
        try:
            return float(v)
        except (TypeError, ValueError):
            return 310.0

    def temp_max(self):
        v = (self.extra.get("defaults") or {}).get("tempMax", 310)
        try:
            return float(v)
        except (TypeError, ValueError):
            return 310.0


TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "task_config.template.json")


def load(raw, cli_overrides=None):
    cli = cli_overrides or {}
    remote = merge(DEFAULT_REMOTE, raw.get("remote", {}))
    process = merge(DEFAULT_PROCESS, raw.get("process", {}))
    # Flat top-level values (what the Flow Console parameter panel saves) are
    # honoured ahead of `defaults`, so a setting made in the UI is the one the
    # run uses instead of the shipped template value.
    d = value_lookup(raw)

    def _fv(value, fallback):
        try:
            return float(value) if value not in (None, "") else float(fallback)
        except (TypeError, ValueError):
            return float(fallback)

    def _iv(value, fallback):
        return int(_fv(value, fallback))

    return TaskConfig(
        remote_dir=cli.get("remote_dir") or raw.get("remoteDir") or "",
        log_prefix=cli.get("log_prefix") or raw.get("logPrefix") or "gromacs_cg",
        num_replicas=_iv(cli.get("num_replicas"), d.int_("numReplicas", 1)),
        steps_per_cycle=_iv(cli.get("steps_per_cycle"), d.int_("stepsPerCycle", 500000)),
        total_cycles=_fv(cli.get("total_cycles"), d.float_("totalCycles", 10)),
        protein=d.str_("protein", "2KY10 SELP CG"),
        remote=remote,
        process=process,
        extra=raw,
    )


def load_config(path):
    with open(path) as f:
        raw = json.load(f)
    return load(raw)


def load_raw(path):
    with open(path) as f:
        return json.load(f)


def write_default(path, remote_dir=None, log_prefix=None):
    return _write_default(
        path, TEMPLATE_PATH, DEFAULT_PROCESS,
        defaults_replicas=1, defaults_steps=500000, defaults_cycles=10,
        remote_dir=remote_dir, log_prefix=log_prefix,
    )
