"""Energy / temperature series from each sample's relax.edr.

Extracts Total-Energy and Temperature with `gmx energy` (one term per call so
column identity is unambiguous), merges on the real energy sample time, and
maps time -> step via step = round(t_ps * 1000 / dt_fs). Writes energy.dat:

  # replica step total_energy(kJ/mol) temperature(K)

Any term missing from the EDR yields empty columns (frontend hides them); the
module only fails when no sample has a readable EDR or gmx is unavailable.
"""
import os
import subprocess

import numpy as np

from _shared.tools import resolve_argv
from lib.analysis import paths, writers

TERMS = ("Total-Energy", "Temperature")


def parse_xvg_numeric(text):
    """Columns of numeric data from a `-xvg none` xvg file (no #/@ lines)."""
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("@"):
            continue
        try:
            rows.append([float(t) for t in line.split()])
        except ValueError:
            continue
    return rows


def gmx_argv(cfg=None):
    """Full argv for GROMACS.

    Goes through the shared resolver so the command is configurable per task
    and so a container-wrapped gmx (which needs `docker exec ... gmx`, not just
    a path) still works. Previously this returned a hardcoded
    /usr/local/gromacs/bin/gmx, which does not exist on the iGEM server -- the
    binary there is /usr/bin/gmx, on PATH -- so this analysis could not run.
    """
    return resolve_argv("gmx", cfg)


def gmx_bin(cfg=None):
    return gmx_argv(cfg)[0]


def extract_series(edr, term, out_xvg, gmx=None, timeout=120):
    """Run `gmx energy` for one term; returns parsed rows or raises.

    `out_xvg` is a temporary path gmx writes the series into. `gmx` may be a
    bare executable name, a full argv list, or None to resolve from the task
    config / environment.
    """
    if gmx is None:
        prefix = gmx_argv()
    elif isinstance(gmx, str):
        prefix = [gmx]
    else:
        prefix = list(gmx)
    cmd = [*prefix, "energy", "-f", edr, "-xvg", "none", "-o", out_xvg]
    proc = subprocess.run(cmd, input=(term + "\n0\n").encode(), capture_output=True,
                          timeout=timeout, cwd=os.path.dirname(out_xvg) or None)
    if proc.returncode != 0:
        raise RuntimeError(f"gmx energy failed ({proc.returncode}): "
                           f"{proc.stderr.decode(errors='replace')[:500]}")
    try:
        with open(out_xvg) as f:
            return parse_xvg_numeric(f.read())
    except OSError as e:
        raise RuntimeError(f"gmx energy produced no output file: {e}")


def analyze(task_dir, cfg):
    """Run the energies module. Returns {ok, samples, rows, error} and writes
    energy.dat under cache/analysis."""
    out = paths.output_dir(task_dir)
    analysis = paths.analysis_dir(task_dir)
    os.makedirs(analysis, exist_ok=True)

    samples = [s for s in paths.discover_samples(out) if paths.edr_path(out, s)]
    if not samples:
        return {"ok": False, "error": "no relax.edr found under output/"}

    dt_fs = cfg.get("timestepFs") or 20
    rows = []
    counts = []
    error = None
    gmx = gmx_argv()
    tmp = os.path.join(analysis, ".energy_xvg")

    for replica, sample in enumerate(samples):
        edr = paths.edr_path(out, sample)
        try:
            series = {}
            for term in TERMS:
                xvg = tmp + "_" + term.replace("-", "_") + ".xvg"
                if os.path.exists(xvg):
                    os.remove(xvg)
                try:
                    parsed = extract_series(edr, term, xvg, gmx)
                    series[term] = {round(row[0], 6): row[1]
                                    for row in parsed if len(row) > 1}
                except Exception as e:
                    error = error or f"replica {replica} {term}: {e}"
                    series[term] = {}
                finally:
                    if os.path.exists(xvg):
                        os.remove(xvg)
            times = sorted(set(series["Total-Energy"]) | set(series.get("Temperature", {})))
            for t in times:
                step = round(t * 1000.0 / dt_fs)
                if step <= 0:
                    continue
                e = series["Total-Energy"].get(t, "")
                t_k = series.get("Temperature", {}).get(t, "")
                rows.append((replica, step,
                             round(e, 2) if e != "" else "",
                             round(t_k, 2) if t_k != "" else ""))
            counts.append(len(rows))
        except Exception as e:
            error = error or f"replica {replica}: {e}"

    writers.write_dat(os.path.join(analysis, "energy.dat"),
                      "replica step total_energy(kJ/mol) temperature(K)", rows)
    return {"ok": bool(rows), "samples": len(samples), "rows": len(rows),
            "error": error}