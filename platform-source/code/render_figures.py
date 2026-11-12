#!/usr/bin/env python3
"""Render the 6 MATLAB 3D field figures without a MATLAB runtime.

`code/plotResults.m` is the canonical plotting code, but neither this machine nor
the `igem` server has MATLAB/Octave installed, so the figures cannot be
regenerated from source there. This script re-renders the same six fields from
the data the MATLAB pipeline already exported:

  * displacement / pore pressure / stress / H  -> code/results_poro_fiber.mat
  * eps_f / E_z                                 -> code/epsf_Ez_byElement.csv

Layout mirrors the reworked plotResults.m: explicit canvas and type sizes sized
for a 150 dpi export, two-line titles (quantity, then units + range), a labelled
colorbar on every panel, and all-English chart text. The previous figures
crammed a long CJK title and an unlabelled colorbar into a ~730 px canvas, which
is why the in-figure annotations were unreadable.

Deviation from plotResults.m: the H field is taken from sol.Hc at cell centres
rather than Hfun(nodes). sol.Hc is the field the run actually used
(H in [435, 455] A/m, matching Hmin), whereas code/H_field.csv is a different
COMSOL export (H in [5e4, 7.5e4] over a 10 mm box) and must not be used here.
Cell-centre sampling also matches the stress / eps_f / E_z panels.

Second deviation: the displacement overlay draws ~1600 subsampled quiver arrows
instead of one per node. plotResults.m passes all 22491 arrows to quiver3, which
at this canvas density renders as a solid grey blob and hides the point cloud it
is meant to annotate.

Usage:  python3 code/render_figures.py [--outdir code/figures]
"""

from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np

# --- type scale (points) -------------------------------------------------
FS_TITLE = 16.0
FS_SUB = 13.0
FS_AX = 13.0
FS_CB = 12.5
FS_CB_TICKS = 11.0
FS_NOTE = 10.5

DPI = 150
FIGSIZE = (11.4, 8.6)  # -> 1710 x 1290 px at 150 dpi

HERE = pathlib.Path(__file__).resolve().parent


def setup_mpl() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    have = {f.name for f in font_manager.fontManager.ttflist}
    # Fall back to a CJK face mainly for the mathtext/unit symbols; titles are
    # English, so DejaVu Sans is the primary face.
    cjk = [
        "Noto Sans CJK JP", "Source Han Sans CN", "Noto Sans CJK SC",
        "Microsoft YaHei", "WenQuanYi Zen Hei", "WenQuanYi Micro Hei",
        "Droid Sans Fallback", "Arial Unicode MS",
    ]
    plt.rcParams["font.sans-serif"] = [f for f in cjk if f in have] + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "dejavusans"


def load_data() -> dict:
    import scipy.io as sio

    mat = HERE / "results_poro_fiber.mat"
    if not mat.exists():
        sys.exit(f"missing {mat}; run the MATLAB pipeline first")
    d = sio.loadmat(mat, squeeze_me=True, struct_as_record=False, simplify_cells=True)
    mesh, sol = d["mesh"], d["sol"]

    data = {
        "nodes": np.asarray(mesh["nodes"], float),
        "L": np.asarray(mesh["L"], float),
        "u": np.asarray(sol["u"], float),
        "p": np.asarray(sol["p"], float).ravel(),
        "xc": np.asarray(sol["xc"], float),
        "sigE": np.asarray(sol["sigE"], float),
        "Hc": np.asarray(sol["Hc"], float).ravel(),
        "note": str(d["Hinfo"]["note"]) if "Hinfo" in d else "",
    }

    csv = HERE / "epsf_Ez_byElement.csv"
    if csv.exists():
        a = np.loadtxt(csv, delimiter=",", skiprows=1)
        data["epsf"] = a[:, 3]
        data["Ez"] = a[:, 4]
    else:
        data["epsf"] = None
        data["Ez"] = None
    return data


def new_3d(d, note: str):
    """Figure with room reserved for title (2 lines), colorbar label and note."""
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=FIGSIZE, dpi=DPI)
    # [left, bottom, width, height]: leaves room for the note under the axes
    ax = fig.add_axes([0.075, 0.135, 0.76, 0.735], projection="3d")
    ax.set_box_aspect(d["L"])
    ax.tick_params(labelsize=FS_CB_TICKS, pad=1)
    ax.set_xlabel("x (mm)", fontsize=FS_AX, labelpad=6)
    ax.set_ylabel("y (mm)", fontsize=FS_AX, labelpad=6)
    ax.set_zlabel("z (mm)", fontsize=FS_AX, labelpad=6)
    ax.grid(True, alpha=0.35)
    if note:
        fig.text(0.075, 0.022, note, fontsize=FS_NOTE, color="0.35", ha="left")
    return fig, ax


def scatter(ax, pts_mm: np.ndarray, values: np.ndarray, size: float) -> None:
    ax.scatter(
        pts_mm[:, 0], pts_mm[:, 1], pts_mm[:, 2],
        c=values, s=size, cmap="jet", vmin=None, vmax=None,
        marker="o", linewidths=0, depthshade=False,
    )


def two_line_title(fig, main: str, sub: str) -> None:
    fig.text(0.075, 0.945, main, fontsize=FS_TITLE, fontweight="bold", ha="left", va="top")
    fig.text(0.075, 0.903, sub, fontsize=FS_SUB, color="0.25", ha="left", va="top")


def attach_colorbar(fig, ax, label: str) -> None:
    """colorbar tied to the mappable on `ax`, in its own reserved axes."""
    cax = fig.add_axes([0.865, 0.135, 0.024, 0.735])
    cb = fig.colorbar(ax.collections[-1], cax=cax)
    cb.set_label(label, fontsize=FS_CB, labelpad=10)
    cb.ax.tick_params(labelsize=FS_CB_TICKS)


def save(fig, outdir: pathlib.Path, name: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / f"{name}.png"
    fig.savefig(p, dpi=DPI, facecolor="white")
    plt_close = __import__("matplotlib.pyplot", fromlist=["close"]).close
    plt_close(fig)
    print(f"wrote {p.name:32} {p.stat().st_size:>8} bytes")


def render(d: dict, outdir: pathlib.Path) -> None:
    import matplotlib.pyplot as plt

    nodes_mm = d["nodes"] * 1e3
    xc_mm = d["xc"] * 1e3
    note = d["note"]
    view = (22, -58)  # readable oblique angle, close to MATLAB's default

    # ---- 1. displacement ------------------------------------------------
    umag = np.sqrt((d["u"] ** 2).sum(axis=1)) * 1e6  # um
    fig, ax = new_3d(d, note)
    scatter(ax, nodes_mm, umag, 1.6)
    # deformation overlay: MATLAB scaled displacement to 5% of the domain
    scale = 0.05 * d["L"].max() / (np.sqrt((d["u"] ** 2).sum(axis=1)).max() + 1e-30)
    defo = (d["nodes"] + scale * d["u"]) * 1e3
    stride = max(1, len(nodes_mm) // 1600)
    ax.quiver(
        nodes_mm[::stride, 0], nodes_mm[::stride, 1], nodes_mm[::stride, 2],
        d["u"][::stride, 0] * 1e6, d["u"][::stride, 1] * 1e6, d["u"][::stride, 2] * 1e6,
        color="0.45", linewidth=0.28, arrow_length_ratio=0.3,
    )
    top = np.abs(d["nodes"][:, 2] - d["L"][2]) < d["L"].max() * 1e-9
    ax.plot(defo[top, 0], defo[top, 1], defo[top, 2], "k.", ms=1.6, zorder=10)
    ax.view_init(*view)
    two_line_title(fig, "Nodal displacement |u|", f"Unit \u00b5m,   max = {umag.max():.4g} \u00b5m")
    attach_colorbar(fig, ax, "|u| (\u00b5m)")
    save(fig, outdir, "Displacement_field")

    # ---- 2. pore pressure ----------------------------------------------
    p = d["p"]
    fig, ax = new_3d(d, note)
    scatter(ax, nodes_mm, p, 1.6)
    ax.view_init(*view)
    if np.abs(p).max() > 0:
        sub = f"Unit Pa,   max|p| = {np.abs(p).max():.4g} Pa"
    else:
        sub = "No fluid load in this case, p \u2261 0 (Pa)"
    two_line_title(fig, "Pore water pressure p_w", sub)
    attach_colorbar(fig, ax, "p_w (Pa)")
    save(fig, outdir, "Pore_pressure")

    # ---- 3. sigma_zz ----------------------------------------------------
    szz = d["sigE"][:, 2] * 1e-3  # kPa (MATLAB sigE(:,3) -> 0-based col 2)
    fig, ax = new_3d(d, note)
    scatter(ax, xc_mm, szz, 2.4)
    ax.view_init(*view)
    two_line_title(fig, "Element-center axial stress \u03c3_zz",
                    f"Unit kPa,   range = [{szz.min():.4g}, {szz.max():.4g}] kPa")
    attach_colorbar(fig, ax, "\u03c3_zz (kPa)")
    save(fig, outdir, "Stress_sigma_zz")

    # ---- 4. magnetic field ----------------------------------------------
    Hn = d["Hc"]
    fig, ax = new_3d(d, note)
    scatter(ax, xc_mm, Hn, 2.4)
    ax.view_init(*view)
    two_line_title(fig, "Applied magnetic field H(x)",
                   f"Unit A/m,   H \u2208 [{Hn.min():.4g}, {Hn.max():.4g}] A/m")
    attach_colorbar(fig, ax, "H (A/m)")
    save(fig, outdir, "Magnetic_field_H(x)")

    # ---- 5. fibre axial strain -----------------------------------------
    if d["epsf"] is None:
        print("skip Fiber_axial_strain_epsf: epsf_Ez_byElement.csv missing")
    else:
        ef = d["epsf"] * 1e6  # um/m
        fig, ax = new_3d(d, note)
        scatter(ax, xc_mm, ef, 2.4)
        ax.view_init(*view)
        two_line_title(fig, "Fiber axial strain \u03b5_f = n_i n_j \u03b5_ij",
                       f"Unit \u00b5m/m,   range = [{ef.min():.4g}, {ef.max():.4g}] \u00b5m/m")
        attach_colorbar(fig, ax, "\u03b5_f (\u00b5m/m)")
        save(fig, outdir, "Fiber_axial_strain_epsf")

    # ---- 6. local Young's modulus --------------------------------------
    if d["Ez"] is None:
        print("skip Local_axial_modulus_E_z: epsf_Ez_byElement.csv missing")
    else:
        Ez = d["Ez"] * 1e-6  # MPa
        fig, ax = new_3d(d, note)
        scatter(ax, xc_mm, Ez, 2.4)
        ax.view_init(*view)
        two_line_title(fig, "Local axial modulus E_z",
                       f"Unit MPa,   mean {Ez.mean():.4g},   "
                       f"range = [{Ez.min():.4g}, {Ez.max():.4g}] MPa")
        attach_colorbar(fig, ax, "E_z (MPa)")
        save(fig, outdir, "Local_axial_modulus_E_z")

    plt.close("all")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(HERE / "figures"))
    args = ap.parse_args()

    setup_mpl()
    d = load_data()
    render(d, pathlib.Path(args.outdir))
    print("done")


if __name__ == "__main__":
    main()
