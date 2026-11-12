"""Render the magnetomech result as a final-simulation PNG.

The field-deformation computation is pure numeric; the deploy host's default
``python3`` may lack matplotlib while the igem2026 conda env has it.  This
module renders the deformation sketch + response curves with matplotlib when it
is available, falling back to a Pillow-only canvas otherwise (so the task never
fails purely because no plot library is installed).
"""
import os


def _f(v, digits=4):
    try:
        if v is None:
            return "n/a"
        return f"{float(v):.{digits}g}"
    except (TypeError, ValueError):
        return "n/a"


def _matplotlib_render(result, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    summary = result.get("summary") or {}
    curves = result.get("curves") or []
    layers = result.get("layers") or []

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))

    # ---- Left: deformation sketch ----
    ax = axes[0]
    ax.axis("off")
    width, height = 1.0, 2.0
    eps_par = summary.get("epsParAtMax", 0.0) or 0.0
    h_new = height * (1.0 + eps_par)
    w_new = width * (1.0 - eps_par / 2.0)
    cx = 1.8
    ax.set_xlim(cx - 1.7, cx + 1.7)
    ax.set_ylim(-height - 0.9, height + 0.9)

    ax.add_patch(plt.Rectangle((cx - width / 2, -height / 2), width, height,
                               fc="#cfe3f7", ec="#1f5fa8", lw=2))
    ax.add_patch(plt.Rectangle((cx - w_new / 2, -h_new / 2), w_new, h_new,
                               fc="#b8d9f0", ec="#1f5fa8", lw=2, ls="--"))
    ax.annotate("", xy=(cx, h_new / 2 + 0.28), xytext=(cx, h_new / 2 + 0.05),
                arrowprops=dict(arrowstyle="->", color="#a11", lw=2))
    ax.annotate("", xy=(cx, -h_new / 2 - 0.28), xytext=(cx, -h_new / 2 - 0.05),
                arrowprops=dict(arrowstyle="->", color="#a11", lw=2))
    ax.annotate("B", xy=(cx + 0.06, 0.42), fontsize=11, color="#a11", fontstyle="italic")
    ax.text(cx, -height - 0.38, "solid: no field\n(contour: applied field)",
            ha="center", va="top", fontsize=9, color="#444")

    contract = summary.get("contractionPctAtMax")
    ax.set_title(f"Final simulation: applied B = {_f(summary.get('appliedBT'))} T\n"
                 f"axial contraction {_f(contract)} %  |  E = {_f(summary.get('youngKpa'))} kPa",
                 fontsize=11)

    # ---- Right: response curves ----
    ax = axes[1]
    if curves:
        hs = [c["h"] for c in curves]
        ms = [c["mEff"] for c in curves]
        eps = [c["epsPar"] for c in curves]
        ax.plot(hs, [m / 1e3 for m in ms], color="#1f5fa8", lw=2, label="Magnetization $M_{\\mathrm{eff}}$ (kA/m)")
        ax2 = ax.twinx()
        ax2.plot(hs, [e * 100.0 for e in eps], color="#2e9e5b", lw=2, ls="--",
                 label="Axial strain $\\Delta L/L$ (%)")
        ax.set_xlabel("Applied field H (A/m)")
        ax.set_ylabel("Magnetization (kA/m)", color="#1f5fa8")
        ax2.set_ylabel("Axial strain (%)", color="#2e9e5b")
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
        ax.grid(alpha=0.3)
    else:
        ax.text(0.5, 0.5, "no curve data", ha="center", va="center")
        ax.axis("off")

    fig.savefig(out_path, dpi=130, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return True


def _pil_render(result, out_path):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1100, 520), "white")
    d = ImageDraw.Draw(img)
    summary = result.get("summary") or {}
    curves = result.get("curves") or []

    d.text((20, 16), "magnetomech final simulation (PIL fallback)", fill="#111")
    lines = [
        "applied B (T):      " + _f(summary.get("appliedBT")),
        "axial contraction %: " + _f(summary.get("contractionPctAtMax")),
        "max contraction %:  " + _f(summary.get("maxContractionPct")),
        "Young E (kPa):      " + _f(summary.get("youngKpa")),
        "modulus source:     " + str(summary.get("modulusSource") or "n/a"),
        "end displacement mm: " + _f(summary.get("endDispMm")),
    ]
    for i, line in enumerate(lines):
        d.text((20, 52 + i * 24), line, fill="#222")

    # Small deformation bar
    if curves:
        eps = [c["epsPar"] for c in curves]
        d.line([(700, 80 + int(abs(e) * 200)) for e in eps], fill="#1f5fa8", width=3)
        d.text((700, 40), "axial strain (scaled)", fill="#444")

    # Deformation box
    eps = summary.get("epsParAtMax", 0.0) or 0.0
    w0, h0 = 120, 260
    cx0, cy0 = 500, 300
    w1 = int(w0 * (1.0 - eps / 2.0))
    h1 = int(h0 * (1.0 + eps))
    d.rectangle([cx0 - w0 // 2, cy0 - h0 // 2, cx0 + w0 // 2, cy0 + h0 // 2], outline="#1f5fa8", width=3)
    d.rectangle([cx0 - w1 // 2, cy0 - h1 // 2, cx0 + w1 // 2, cy0 + h1 // 2], outline="#2e9e5b", width=2)
    d.text((cx0 - 40, cy0 - h1 // 2 - 30), "deformation", fill="#2e9e5b")

    img.save(out_path, "PNG")
    return True


def render_final_image(result, out_dir):
    """Write out_dir/final_simulation.png. Returns the filename or None."""
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "final_simulation.png")
    for renderer in (_matplotlib_render, _pil_render):
        try:
            if renderer(result, out_path):
                return "final_simulation.png"
        except Exception:
            continue
    return None