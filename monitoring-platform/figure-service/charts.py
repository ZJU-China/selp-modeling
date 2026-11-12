#!/usr/bin/env python3
"""Render SELP task figures as SVG from the platform's actual data files.

Each chart function receives a task mapping (see tasks.json) and returns a
matplotlib Figure. The HTTP service in server.py turns these into SVG.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

INK = "#1d1d1f"
MUTED = "#6e6e73"
HAIR = "#d2d2d7"
BLUE = "#0066cc"
GREY = "#6e6e73"
LIGHT = "#8ab8e8"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 12.5,
    "axes.edgecolor": HAIR,
    "axes.linewidth": 0.8,
    "axes.labelcolor": MUTED,
    "axes.labelsize": 12,
    "axes.titlecolor": INK,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": 11,
    "ytick.labelsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "legend.frameon": False,
    "legend.fontsize": 11,
    "lines.solid_capstyle": "round",
    "svg.fonttype": "none",
    "savefig.bbox": "tight",
})


def _csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def _tsv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _num(rows, key):
    return np.array([float(r[key]) for r in rows], dtype=float)


def _titles(ax, title, ylabel=None, xlabel=None):
    ax.set_title(title, loc="left", color=INK, pad=8)
    if ylabel:
        ax.set_ylabel(ylabel)
    if xlabel:
        ax.set_xlabel(xlabel)


def _spec(rows):
    order = []
    for r in rows:
        if r["species"] not in order:
            order.append(r["species"])
    return order


def calibration(task):
    data = json.loads(Path(task["calibration"]).read_text())
    rows = data["rows"]
    species = _spec(rows)
    colors = {species[0]: BLUE}
    if len(species) > 1:
        colors[species[1]] = GREY
    for s in species[2:]:
        colors[s] = LIGHT

    fig, ax = plt.subplots(figsize=(7.6, 5.0))
    vals = [float(r["empirical_E_kPa"]) for r in rows]
    xs = np.arange(len(rows))
    bars = ax.bar(xs, vals, width=0.58, color=[colors[r["species"]] for r in rows], zorder=2)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v - 1.4, f"{v:.2f}",
                ha="center", va="top", fontsize=9.5, color="white")

    for s in species:
        idx = [i for i, r in enumerate(rows) if r["species"] == s]
        mean = float(data["means"][s]["mean_kPa"])
        ax.plot([idx[0] - 0.45, idx[-1] + 0.45], [mean, mean], color=INK, lw=1.1, ls=(0, (4, 3)), zorder=3)
        ax.plot(sum(idx) / len(idx), mean, marker="D", markersize=5, markerfacecolor="white",
                markeredgecolor=INK, markeredgewidth=1.2, ls="none", zorder=4)


    ax.set_xticks(xs, [f"{r['species']}\n{r['branch']}" for r in rows])
    ax.set_ylim(0, max(vals) * 1.16)
    ax.yaxis.set_major_locator(MaxNLocator(6))
    ax.margins(x=0.10)
    _titles(ax, "Calibrated branch moduli", "Compressive modulus (kPa)")
    return fig


def md_controls(task):
    blocks = json.loads(Path(task["md_block_means"]).read_text())
    fig, axes = plt.subplots(2, 1, figsize=(8.6, 5.4), sharex=True)
    groups = {}
    for b in blocks:
        groups.setdefault(b["species"], {}).setdefault(b["branch"], []).append(b)

    colors = {list(groups)[0]: BLUE}
    if len(groups) > 1:
        colors[list(groups)[1]] = GREY

    for species, branches in groups.items():
        times = np.array(sorted({float(x["block_start_ns"]) for br in branches.values() for x in br}))
        temp = np.full((len(branches), len(times)), np.nan)
        conc = np.full((len(branches), len(times)), np.nan)
        for i, br in enumerate(branches.values()):
            for x in br:
                j = int(np.where(times == float(x["block_start_ns"]))[0][0])
                temp[i, j] = float(x["temperature_mean_K"])
                conc[i, j] = float(x["concentration_mean_mg_ml"])
        for ax, mat, label in ((axes[0], temp, "Temperature (K)"),
                               (axes[1], conc, "Concentration (mg/mL)")):
            mean = np.nanmean(mat, axis=0)
            lo, hi = np.nanmin(mat, axis=0), np.nanmax(mat, axis=0)
            ax.fill_between(times, lo, hi, color=colors[species], alpha=0.14, linewidth=0)
            ax.plot(times, mean, color=colors[species], lw=1.4, label=species)
            ax.set_ylabel(label)
    axes[0].legend(loc="upper right", ncol=2)
    axes[0].set_title("Network temperature and concentration", loc="left", color=INK, pad=8)
    axes[1].set_xlabel("Simulation time (ns)")
    return fig


def famd_metrics(task):
    rows = _csv(task["famd_metrics"])
    t = _num(rows, "time_ns")
    fig, axes = plt.subplots(2, 2, figsize=(9.6, 6.0))
    ax = axes[0][0]
    ax.plot(t, _num(rows, "actual_temperature_K"), color=BLUE, lw=1.0)
    _titles(ax, "Temperature", "K", None)
    ax = axes[0][1]
    ax.plot(t, _num(rows, "potential_kcal_mol"), color=BLUE, lw=1.0)
    _titles(ax, "Potential energy", "kcal/mol", None)
    ax = axes[1][0]
    ax.plot(t, _num(rows, "Rg_nm"), color=BLUE, lw=1.0, label="Rg")
    _titles(ax, "Radius of gyration", "nm", "Time (ns)")
    ax = axes[1][1]
    ax.plot(t, _num(rows, "RMSD_to_first_nm"), color=BLUE, lw=1.0)
    _titles(ax, "Cα RMSD to first frame", "nm", "Time (ns)")
    fig.tight_layout(h_pad=2.0, w_pad=2.0)
    return fig


def rmsd(task):
    rows = _csv(task["famd_metrics"])
    fig, ax = plt.subplots(figsize=(8.0, 3.8))
    ax.plot(_num(rows, "time_ns"), _num(rows, "RMSD_to_first_nm"), color=BLUE, lw=1.2)
    _titles(ax, "Cα RMSD of the 2KY10 reference stream", "nm", "Time (ns)")
    ax.margins(x=0)
    return fig


def temperature_walks(task):
    rows = _tsv(task["temperature_walks"])
    reps = sorted({int(r["replica"]) for r in rows})
    palette = [BLUE, "#4a90d9", GREY, "#b0b0b5"]
    fig, ax = plt.subplots(figsize=(9.2, 3.2))
    for i, rep in enumerate(reps):
        sub = [r for r in rows if int(r["replica"]) == rep]
        xs = np.array([float(r["time_ns"]) for r in sub])
        ys = np.array([float(r["target_temperature_K"]) for r in sub])
        ax.step(xs, ys, where="post", color=palette[i % len(palette)], lw=1.2, label=f"R{rep}")
    ax.set_ylim(260, 410)
    ax.set_xlim(float(rows[0]["time_ns"]), float(rows[-1]["time_ns"]))
    ax.set_xlabel("Time (ns)")
    ax.set_ylabel("Target (K)")
    ax.set_title("Replica temperature assignments", loc="left", color=INK, pad=8)
    ax.legend(loc="upper left", ncol=4)
    return fig


def em(task):
    rows5 = _csv(task["em_2ky5"])
    rows10 = _csv(task["em_2ky10"])
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.8))
    ax = axes[0]
    ax.plot(_num(rows5, "minimization_step"), _num(rows5, "potential_kJ_mol"), color=BLUE, marker="o", ms=3)
    _titles(ax, "2KY5: vacuum minimization", "Potential energy (kJ/mol)", "Minimization step")
    ax = axes[1]
    ax.plot(_num(rows10, "segment"), _num(rows10, "Fmax_kJ_mol_nm"), color=GREY)
    _titles(ax, "2KY10: segmented minimization", "Max force (kJ/mol/nm)", "Segment")
    fig.tight_layout(w_pad=3)
    return fig


def nvt(task):
    thermo = _csv(task["nvt_thermo"])
    pot = _csv(task["nvt_potential"])
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.8))
    ax = axes[0]
    ax.plot(_num(thermo, "time_ps"), _num(thermo, "temperature_K"), color=BLUE, lw=1.0)
    _titles(ax, "NVT temperature", "K", "Time (ps)")
    ax = axes[1]
    ax.plot(_num(pot, "time_ps"), _num(pot, "potential_kJ_mol"), color=BLUE, lw=1.0)
    _titles(ax, "NVT potential energy", "kJ/mol", "Time (ps)")
    fig.tight_layout(w_pad=3)
    return fig


def npt(task):
    thermo = _csv(task["npt_thermo"])
    pot = _csv(task["npt_potential"])
    t = _num(thermo, "absolute_preparation_time_ps")
    fig, axes = plt.subplots(1, 3, figsize=(10.6, 3.6))
    ax = axes[0]
    ax.plot(t, _num(thermo, "temperature_K"), color=BLUE, lw=1.0)
    _titles(ax, "Temperature", "K", "Time (ps)")
    ax = axes[1]
    ax.plot(t, _num(thermo, "pressure_bar"), color=BLUE, lw=0.8)
    _titles(ax, "Pressure", "bar", "Time (ps)")
    ax = axes[2]
    ax.plot(_num(pot, "absolute_preparation_time_ps"), _num(pot, "potential_kJ_mol"), color=BLUE, lw=1.0)
    _titles(ax, "Potential energy", "kJ/mol", "Time (ps)")
    fig.tight_layout(w_pad=2.4)
    return fig


def step_min(task):
    d = Path(task["prep_dir"])
    vac = _csv(d / "01_minimize_vacuum.csv")
    gbis = _csv(d / "02_minimize_gbis.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6))
    axes[0].plot(_num(vac, "step"), _num(vac, "potential_kcal_mol"), color=BLUE, lw=1.0)
    _titles(axes[0], "Vacuum minimization", "kcal/mol", "Step")
    axes[1].plot(_num(gbis, "step"), _num(gbis, "potential_kcal_mol"), color=BLUE, lw=1.0)
    _titles(axes[1], "GBIS minimization", "kcal/mol", "Step")
    fig.tight_layout(w_pad=3)
    return fig


def step_warm(task):
    rows = _csv(Path(task["prep_dir"]) / "03_gbis_warm_025fs.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.4))
    axes[0].plot(_num(rows, "stage_ps"), _num(rows, "temperature_K"), color=BLUE, lw=1.0)
    _titles(axes[0], "Warm-up temperature", "K", "Time (ps)")
    axes[1].plot(_num(rows, "stage_ps"), _num(rows, "potential_kcal_mol"), color=BLUE, lw=1.0)
    _titles(axes[1], "Warm-up potential energy", "kcal/mol", "Time (ps)")
    fig.tight_layout(w_pad=3)
    return fig


def step_prep(task):
    d = Path(task["prep_dir"])
    stages = [("04_gbis_eq_050fs.csv", "0.5 fs"), ("05_gbis_eq_1fs.csv", "1 fs"),
              ("06_gbis_eq_2fs.csv", "2 fs"), ("07_gbis_eq_4fs.csv", "4 fs")]
    fig, axes = plt.subplots(1, 4, figsize=(10.6, 3.2), sharey=True)
    for ax, (name, label) in zip(axes, stages):
        rows = _csv(d / name)
        ax.plot(_num(rows, "stage_ps"), _num(rows, "temperature_K"), color=BLUE, lw=1.0)
        _titles(ax, label, "K" if ax is axes[0] else None, "ps")
    fig.suptitle("Timestep ramp: temperature", x=0.01, ha="left", color=INK, fontsize=11, fontweight="bold")
    fig.tight_layout(w_pad=1.6)
    return fig


CHARTS = {
    "calibration": calibration,
    "md-controls": md_controls,
    "famd-metrics": famd_metrics,
    "rmsd": rmsd,
    "temperature-walks": temperature_walks,
    "em": em,
    "nvt": nvt,
    "npt": npt,
    "step-min": step_min,
    "step-warm": step_warm,
    "step-prep": step_prep,
}
