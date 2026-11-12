#!/usr/bin/env python3
"""Render task figures from metadata with semantic, merged charts.

Rules:
  * NAMD log files are parsed into total energy and temperature time series.
    Logs for the same replica are concatenated by step; replicas are drawn as
    separate lines in ONE chart titled "Total energy" / "Temperature".
  * GROMACS .xvg files are grouped by metric. Time-ordered segments of the same
    branch are concatenated; branches are drawn as separate lines. Titles come
    from the metric ("Network distances", "Temperature"), not the filename.
  * CSV / JSON figures are titled by the plotted quantity.
  * Derived CSVs that duplicate a native platform chart are not listed.
"""
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

INK = "#1d1d1f"
MUTED = "#6e6e73"
HAIR = "#d2d2d7"
BLUE = "#0066cc"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11,
    "axes.edgecolor": HAIR, "axes.linewidth": 0.8,
    "axes.labelcolor": MUTED, "axes.titlecolor": INK,
    "axes.titlesize": 12, "axes.titleweight": "bold",
    "xtick.color": MUTED, "ytick.color": MUTED,
    "xtick.labelsize": 9, "ytick.labelsize": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white",
    "legend.frameon": False, "svg.fonttype": "none", "savefig.bbox": "tight",
})

MAX_FIGURES = 12
MAX_DEPTH = 4
COLORS = ["#0066cc", "#34a853", "#f29900", "#d93025"]
TIME_HINTS = re.compile(r"time|ps|ns|step|cycle|frame|iteration", re.I)
SERIES_ORDER = [
    ("temp", "Temperature"), ("potential", "Potential"), ("empirical", "Empirical modulus"), ("energy", "Energy"),
    ("rmsd", "RMSD"), ("rg", "Rg"), ("distance", "Distance"),
    ("h_aperm", "Field"), ("epspar", "Strain"), ("modulus", "Modulus"),
]


def walk_files(root):
    root = Path(root).resolve()
    out, seen = [], set()
    for base, dirs, files in os.walk(root, followlinks=True):
        real = os.path.realpath(base)
        if real in seen:
            dirs[:] = []
            continue
        seen.add(real)
        rel = Path(base).relative_to(root)
        if len(rel.parts) >= MAX_DEPTH:
            dirs[:] = []
        for name in files:
            if not name.endswith((".xvg", ".csv", ".json", ".jsonl", ".log", ".out")):
                continue
            p = Path(base) / name
            try:
                if p.stat().st_size > 60_000_000 or p.stat().st_size < 80:
                    continue
            except OSError:
                continue
            out.append(p)
    return out


def xvg_rows(path):
    data = []
    for line in Path(path).read_text(errors="ignore").splitlines():
        s = line.strip()
        if not s or s[0] in "#@":
            continue
        try:
            data.append([float(x) for x in s.split()])
        except ValueError:
            continue
    return data


def csv_data(path):
    with open(path, newline="", errors="ignore") as fh:
        rows = list(csv.reader(fh))
    if len(rows) < 2:
        return None
    header, body = rows[0], rows[1:]
    if not body:
        return None
    width = min(len(r) for r in body)
    numeric = []
    for i in range(width):
        try:
            vals = np.array([float(r[i]) for r in body])
        except ValueError:
            continue
        numeric.append((i, vals))
    if not numeric:
        return None
    return header, numeric


def parse_log(path):
    """Return list of (step, total_energy, temperature)."""
    names = None
    rows = []
    for line in Path(path).read_text(errors="ignore").splitlines():
        if line.startswith("ETITLE:"):
            names = line[7:].split()
            continue
        if not line.startswith("ENERGY:"):
            continue
        parts = line[7:].split()
        if names and len(parts) >= len(names):
            info = dict(zip(names, parts))
            try:
                rows.append((int(float(info.get("TS", len(rows)))), float(info.get("TOTAL")), float(info.get("TEMP"))))
            except (TypeError, ValueError):
                continue
        elif len(parts) >= 13:
            try:
                rows.append((int(float(parts[0])), float(parts[10]), float(parts[11])))
            except ValueError:
                continue
    return rows


def replica_of(path):
    m = re.search(r"\.(\d)\.log$", path.name)
    if m:
        return m.group(1)
    parent = path.parent.name
    if parent.isdigit():
        return parent
    return "0"


def xvg_legends(path):
    legends = []
    for line in Path(path).read_text(errors="ignore").splitlines():
        m = re.search(r'@ s\d+ legend "([^"]+)"', line)
        if m:
            legends.append(m.group(1))
    return legends


def xvg_series(path, metric):
    rows = [r for r in xvg_rows(path) if len(r) >= 2]
    if not rows:
        return None
    arr = np.array(rows)
    if metric == "temperature":
        legends = xvg_legends(path)
        for i, name in enumerate(legends):
            if "temp" in name.lower():
                col = i + 1
                if col < arr.shape[1]:
                    return arr[:, 0], arr[:, col]
    return arr[:, 0], np.nanmean(arr[:, 1:], axis=1)


def branch_label(rel):
    parts = rel.split("/")
    for p in parts[:-1]:
        if re.search(r"[A-Za-z]", p):
            return re.sub(r"\d{3,}", "", p).strip("_") or p
    return "series"


def pretty_title(name):
    low = name.lower().replace(" ", "_")
    if "e_kpa" in low or "modulus" in low:
        if "frozen" in low:
            return "Frozen empirical modulus (kPa)"
        if "empirical" in low:
            return "Empirical modulus (kPa)"
        return "Modulus (kPa)"
    if "fraction" in low:
        return re.sub(r"[_-]+", " ", name).strip().title()
    return re.sub(r"[_-]+", " ", name).strip().title()


def pick_quantity(cols, exclude):
    for stem_key, _ in SERIES_ORDER:
        for name in cols:
            if name != exclude and stem_key in name.lower():
                return name
    return next((k for k in cols if k != exclude), exclude)


def smooth(vals, window):
    if window <= 1 or len(vals) < window:
        return vals
    v = np.asarray(vals, dtype=float)
    kernel = np.ones(window, dtype=float) / window
    pad = window // 2
    padded = np.pad(v, pad, mode="edge")
    out = np.convolve(padded, kernel, mode="valid")
    return out[:len(v)]


def bin_series(xs, ys, bins=400):
    """Down-sample a noisy per-step series into bin means.

    TIGER2 exchanges make the instantaneous temperature jump every cycle, so
    connecting every frame draws a wall of vertical segments. Binning keeps the
    trend (and removes duplicate/overlapping restart frames) without hiding the
    sampling range.
    """
    if len(xs) <= bins:
        return xs, ys
    arr = np.asarray(xs, dtype=float)
    vals = np.asarray(ys, dtype=float)
    order = np.argsort(arr, kind="stable")
    arr, vals = arr[order], vals[order]
    edges = np.linspace(arr[0], arr[-1], bins + 1)
    idx = np.clip(np.searchsorted(edges, arr, side="right") - 1, 0, bins - 1)
    bx, by = [], []
    for b in range(bins):
        mask = idx == b
        if not mask.any():
            continue
        bx.append(float(arr[mask].mean()))
        by.append(float(vals[mask].mean()))
    return bx, by


def metric_from_name(name):
    low = name.lower()
    stem = re.sub(r"part\d+", "", low)
    stem = re.sub(r"^md[._]?", "", stem).strip("._-")
    if "pullf" in stem:
        return ("pullf", "Pull force")
    if "pullx" in stem:
        return ("pullx", "Pull x")
    if "distance" in stem:
        return ("distances", "Network distances")
    if "thermo" in stem:
        return ("temperature", "Temperature")
    if "startup" in stem:
        return ("startup_energy", "Startup energy")
    return (stem, re.sub(r"[_-]+", " ", stem).title())


def scan(roots, mode="generic", task_name=""):
    if isinstance(roots, (str, Path)):
        roots = [roots]
    specs = []
    log_files, xvg_files, csv_files, json_files, jsonl_files = [], [], [], [], []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for p in walk_files(root):
            rel = os.path.relpath(str(p), str(root))
            low = p.name.lower()
            full = str(p).lower()
            if "/temp/" in full or "logs_archive" in full or "/archive" in full or "historical" in full:
                continue
            if str(p).endswith("/analysis/thermo.csv") or low in ("magnetomech.curve.csv", "magnetomech.layer.csv"):
                continue
            if p.suffix in (".log", ".out"):
                log_files.append((p, rel))
            elif p.suffix == ".xvg":
                xvg_files.append((p, rel))
            elif p.suffix == ".csv":
                csv_files.append((p, rel))
            elif p.suffix == ".json":
                json_files.append((p, rel))
            elif p.suffix == ".jsonl":
                jsonl_files.append((p, rel))

    if mode == "tiger2":
        xvg_files, csv_files, json_files, jsonl_files = [], [], [], []
    elif mode == "gromacs_cg":
        log_files, csv_files, json_files, jsonl_files = [], [], [], []
    elif mode == "magnetomech":
        log_files, jsonl_files = [], []
        blocked = ("pull", "network_sampling", "warming", "density_correction", "precursor", "cold_preparation", "startup")
        xvg_files = [(p, r) for p, r in xvg_files if not any(b in str(p).lower() for b in blocked)]
    elif mode == "e2e":
        csv_files, json_files = [], []

    prod_logs = [(p, r) for p, r in log_files if "/production/" in str(p)]
    if prod_logs:
        log_files = prod_logs

    # --- logs: one chart per metric, one line per replica ---
    per_metric = {"total_energy": {}, "temperature": {}}
    for p, rel in log_files:
        rows = parse_log(p)
        if len(rows) < 3:
            continue
        rep = replica_of(p)
        for idx, key in ((1, "total_energy"), (2, "temperature")):
            pts = [(r[0], r[idx]) for r in rows if r[idx] is not None]
            if len(pts) >= 3:
                per_metric[key].setdefault(rep, []).append((p, pts))
    for key, label in (("total_energy", "Total energy"), ("temperature", "Temperature")):
        reps = per_metric[key]
        members, sources = [], []
        for rep, chunks in sorted(reps.items()):
            # one continuous run per replica; keep replicas separate for Control
            best = max(chunks, key=lambda c: len(c[1]))
            xs, ys = [], []
            for x, y in best[1]:
                xs.append(x)
                ys.append(y)
            if not xs:
                continue
            bx, by = bin_series(xs, ys, bins=80)
            members.append({"label": "replica " + rep, "x": bx, "y": by,
                            "paths": [str(best[0])]})
            sources.append(str(best[0]))
        if not members:
            continue
        fid = "metric-" + key.replace("_", "-") + "-" + hashlib.sha1("|".join(sources).encode()).hexdigest()[:6]
        specs.append({
            "id": fid, "title": label, "kind": "multiline", "metric": key,
            "xlabel": "step", "ylabel": "Temperature (K)" if key == "temperature" else "Total energy (kcal/mol)",
            "members": members, "sources": sources,
            "points": sum(len(m["x"]) for m in members),
            "script": "figures-service/render_task.py",
        })

    # --- xvg: group by metric, concatenate segments per branch, overlay branches ---
    groups = {}
    for p, rel in xvg_files:
        metric, title = metric_from_name(p.name)
        groups.setdefault((metric, title), []).append((p, rel))
    for (metric, title), items in groups.items():
        branches = {}
        for p, rel in items:
            branches.setdefault(branch_label(rel), []).append((p, rel))
        members = []
        for branch, chunks in sorted(branches.items()):
            chunks.sort(key=lambda pr: pr[1])
            xs, ys = [], []
            for p, rel in chunks:
                got = xvg_series(p, metric)
                if not got:
                    continue
                xs.extend(got[0].tolist())
                ys.extend(got[1].tolist())
            if xs:
                ys = np.asarray(smooth(ys, max(1, len(ys) // 200)), dtype=float).tolist()
                members.append({"label": branch, "x": xs, "y": ys,
                                "paths": [str(pp) for pp, _ in chunks]})
        if members:
            sources = [pp for m in members for pp in m.get("paths", [])]
            safe_metric = re.sub(r"[^a-z0-9-]", "-", metric.lower())
            fid = "metric-" + safe_metric + "-" + hashlib.sha1("|".join(sources).encode()).hexdigest()[:6]
            specs.append({
                "id": fid, "title": title, "kind": "multiline", "metric": metric,
                "xlabel": "time (ps)",
                "ylabel": {"distances": "Distance (nm)", "temperature": "Temperature (K)",
                           "pullf": "Pull force (kJ mol$^{-1}$ nm$^{-1}$)", "pullx": "Reaction coordinate (nm)"}.get(metric, title),
                "members": members, "sources": sources,
                "points": sum(len(m["x"]) for m in members),
                "script": "figures-service/render_task.py",
            })

    # --- CSV / JSON: title by plotted quantity ---
    for p, rel in csv_files:
        data = csv_data(p)
        if not data:
            continue
        header, numeric = data
        cols = {}
        for idx, vals in numeric:
            name = header[idx] if idx < len(header) and header[idx] else "col %d" % (idx + 1)
            cols[name] = vals
        if not cols:
            continue
        numeric_idx = {i for i, _ in numeric}
        with open(p, newline="", errors="ignore") as fh:
            raw = list(csv.reader(fh))
        body = raw[1:] if len(raw) > 1 else []

        lower_header = [h.strip().lower() for h in header]

        def label_of(row):
            if "species" in lower_header and "branch" in lower_header:
                si = lower_header.index("species")
                bi = lower_header.index("branch")
                if si < len(row) and bi < len(row):
                    return "%s %s" % (str(row[si]).strip(), str(row[bi]).strip())
            parts = []
            for j, h in enumerate(header):
                if j in numeric_idx:
                    continue
                if j < len(row):
                    val = str(row[j]).strip()
                    if val and len(val) < 40 and not re.fullmatch(r"[0-9a-f]{16,}", val):
                        parts.append(val)
            return " ".join(parts)

        cat_idx = None
        for cand in ("species", "branch", "chain_i", "chain", "sample"):
            if cand in [h.strip().lower() for h in header]:
                cat_idx = [h.strip().lower() for h in header].index(cand)
                break
        yname = pick_quantity(cols, None)
        title = pretty_title(yname) or p.stem
        fid = "csv-" + hashlib.sha1(rel.encode()).hexdigest()[:8]
        if cat_idx is not None and yname in cols and body:
            names = []
            vals = {}
            for row in body:
                if cat_idx >= len(row):
                    continue
                lab = label_of(row) if header[cat_idx].strip().lower() != "chain_i" else str(row[cat_idx])
                try:
                    v = float(row[header.index(yname)]) if yname in header else None
                except ValueError:
                    v = None
                if v is None or not lab:
                    continue
                names.append(lab)
                vals.setdefault(lab, []).append(v)
            order, means = [], []
            for lab in names:
                if lab in vals:
                    order.append(lab)
                    means.append(float(np.mean(vals[lab])))
                    del vals[lab]
            key = re.sub(r"[^a-z0-9]", "", task_name.lower())
            species = re.search(r"(2ky\d+)", key)
            if species and order:
                want = species.group(1)
                filtered = [(a, b) for a, b in zip(order, means)
                            if want in re.sub(r"[^a-z0-9]", "", a.lower())]
                if filtered:
                    order = [a for a, _ in filtered]
                    means = [b for _, b in filtered]
            if order:
                specs.append({"id": fid, "title": title, "kind": "bar", "path": str(p),
                              "sources": [str(p)], "labels": order, "values": means,
                              "xlabel": header[cat_idx].strip() or "category",
                              "ylabel": yname, "points": len(order),
                              "script": "figures-service/render_task.py"})
                continue
        def varying(n):
            return float(np.ptp(cols[n])) > 0
        xname = next((k for k in cols if TIME_HINTS.search(k) and varying(k)), None)
        if xname is None:
            xname = next((k for k in cols if varying(k)), next(iter(cols)))
        title = pretty_title(yname) or p.stem
        specs.append({"id": fid, "title": title, "kind": "csv", "path": str(p), "sources": [str(p)],
                      "points": int(len(cols[yname])),
                      "script": "figures-service/render_task.py"})

    for p, rel in json_files:
        if "frozen_calibration" in rel or "handoff_snapshot" in rel:
            continue
        try:
            obj = json.loads(p.read_text())
        except Exception:
            continue
        rows = obj.get("rows") if isinstance(obj, dict) else None
        if not isinstance(rows, list) or not rows:
            continue
        keys = []
        for r in rows:
            for k, v in r.items():
                if isinstance(v, (int, float)) and k not in keys:
                    keys.append(k)
        if not keys:
            continue
        preferred = pick_quantity({k: 1 for k in keys}, None)
        title = pretty_title(preferred)
        fid = "json-" + hashlib.sha1(rel.encode()).hexdigest()[:8]
        specs.append({"id": fid, "title": title, "kind": "json", "path": str(p), "key": preferred,
                      "sources": [str(p)], "points": len(rows),
                      "script": "figures-service/render_task.py"})

    for p, rel in jsonl_files:
        pts = []
        try:
            for line in p.read_text(errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if "step" in obj and "e2e_nm" in obj:
                    pts.append((float(obj["step"]), float(obj["e2e_nm"])))
        except Exception:
            continue
        if len(pts) >= 3:
            fid = "jsonl-" + hashlib.sha1(rel.encode()).hexdigest()[:8]
            specs.append({
                "id": fid, "title": "End-to-end distance", "kind": "multiline",
                "metric": "e2e", "members": [{"label": "e2e", "x": [a for a, _ in pts], "y": [b for _, b in pts], "path": str(p)}],
                "sources": [str(p)], "points": len(pts),
                "script": "figures-service/render_task.py",
            })

    if mode == "magnetomech":
        keep, seen = [], {}
        for spec in specs:
            if spec["kind"] in ("csv", "json", "bar"):
                t = spec["title"].lower()
                if spec["kind"] == "json":
                    continue
                if "modulus" not in t and "energy fraction" not in t:
                    continue
                if spec.get("points", 0) < 3:
                    continue
                base = spec["title"].split(" —")[0]
                if base in seen:
                    if spec.get("points", 0) > seen[base].get("points", 0):
                        seen[base].update(spec)
                    continue
                seen[base] = spec
            keep.append(spec)
        specs = keep

    for spec in specs:
        if mode in ("tiger2", "e2e") and spec.get("metric") in ("temperature", "total_energy", "e2e"):
            spec["section"] = "control"
        else:
            spec["section"] = "results"

    now = __import__("time").time()
    for spec in specs:
        paths = spec.get("sources") or ([spec.get("path")] if spec.get("path") else [])
        mtimes = []
        for path in paths:
            try:
                mtimes.append(os.path.getmtime(path))
            except OSError:
                pass
        running = bool(mtimes) and (now - max(mtimes) < 1800)
        points = spec.get("points", 0)
        spec["status"] = "running" if running else ("partial" if points < 200 else "complete")

    seen = {}
    for spec in specs:
        seen[spec["title"]] = seen.get(spec["title"], 0) + 1
    for spec in specs:
        if seen.get(spec["title"], 0) > 1:
            src = spec.get("path") or (spec.get("sources") or [""])[0]
            spec["title"] = spec["title"] + " — " + os.path.basename(src).rsplit(".", 1)[0]
    counts = {}
    for spec in specs:
        counts[spec["title"]] = counts.get(spec["title"], 0) + 1
    for spec in specs:
        if counts.get(spec["title"], 0) > 1:
            src = spec.get("path") or (spec.get("sources") or [""])[0]
            parent = os.path.basename(os.path.dirname(src))
            if parent and parent not in spec["title"]:
                spec["title"] = spec["title"] + " (" + parent + ")"
    specs.sort(key=lambda s: (s["kind"] != "multiline", s["title"]))
    return specs[:MAX_FIGURES]


def render(spec):
    fig, ax = plt.subplots(figsize=(7.8, 4.0))
    try:
        fig.set_layout_engine("constrained")
    except Exception:
        pass
    kind = spec["kind"]
    plotted = False

    if kind == "band":
        x = np.asarray(spec["x"], dtype=float)
        mean = np.asarray(spec["mean"], dtype=float)
        lo = np.asarray(spec["lo"], dtype=float)
        hi = np.asarray(spec["hi"], dtype=float)
        ax.fill_between(x, lo, hi, color=BLUE, alpha=0.18, linewidth=0)
        ax.plot(x, mean, color=BLUE, lw=1.4)
        ax.set_xlabel("step")
        ax.set_ylabel(spec["title"])
        plotted = True

    elif kind == "multiline":
        for i, m in enumerate(spec["members"]):
            x = np.asarray(m["x"], dtype=float)
            y = np.asarray(m["y"], dtype=float)
            order = np.argsort(x, kind="stable")
            keep = len(x) - 1 - np.unique(x[::-1], return_index=True)[1]
            x, y = x[order][keep], y[order][keep]
            ax.plot(x, y, lw=1.1, color=COLORS[i % len(COLORS)], label=m["label"])
        ax.set_xlabel(spec.get("xlabel", "step"))
        ax.set_ylabel(spec.get("ylabel", spec["title"]))
        if len(spec["members"]) > 1:
            ax.legend(loc="best", fontsize=8)
        plotted = True

    elif kind == "bar":
        labels = spec.get("labels", [])
        vals = np.asarray(spec.get("values", []), dtype=float)
        ax.bar(range(len(vals)), vals, color=BLUE, width=0.7)
        ax.set_xticks(range(len(vals)), labels,
                      rotation=45 if len(labels) > 6 else 0, ha="right" if len(labels) > 6 else "center")
        ax.set_xlabel(spec.get("xlabel", "category"))
        ax.set_ylabel(spec.get("ylabel", spec["title"]))
        plotted = True

    elif kind == "csv":
        data = csv_data(spec["path"])
        if data:
            header, numeric = data
            cols = {}
            for idx, vals in numeric:
                name = header[idx] if idx < len(header) and header[idx] else "col %d" % (idx + 1)
                cols[name] = vals
            def varying(n):
                return float(np.ptp(cols[n])) > 0
            xname = next((k for k in cols if TIME_HINTS.search(k) and varying(k)), None)
            if xname is None:
                xname = next((k for k in cols if varying(k)), next(iter(cols)))
            yname = next((k for k in cols if k != xname and any(s in k.lower() for s, _ in SERIES_ORDER)), None)
            if yname is None:
                yname = next((k for k in cols if k != xname), xname)
            ax.plot(cols[xname], cols[yname], color=BLUE, lw=1.2)
            ax.set_xlabel(xname)
            ax.set_ylabel(yname)
            plotted = True

    elif kind == "json":
        obj = json.loads(Path(spec["path"]).read_text())
        rows = obj.get("rows") or []
        key = spec["key"]
        vals = [float(r[key]) for r in rows if isinstance(r.get(key), (int, float))]
        ax.bar(range(len(vals)), vals, color=BLUE, width=0.6)
        ax.set_xticks(range(len(vals)), [str(r.get("branch", i + 1)) for i, r in enumerate(rows)])
        ax.set_xlabel("branch")
        ax.set_ylabel(key)
        plotted = True

    if not plotted:
        plt.close(fig)
        return None
    ax.set_title(spec["title"], loc="left")
    ax.margins(x=0.01)
    return fig


def main():
    args = sys.argv[1:]
    task_type = task_name = ""
    if "--task-type" in args:
        i = args.index("--task-type"); task_type = args[i + 1]; del args[i:i + 2]
    if "--task-name" in args:
        i = args.index("--task-name"); task_name = args[i + 1]; del args[i:i + 2]
    mode = task_type
    if "e2e" in task_name.lower():
        mode = "e2e"
    if len(args) >= 2 and args[0] == "--list":
        print(json.dumps({"figures": scan(args[1:], mode, task_name)}))
        return
    if len(args) >= 2:
        roots, fid = [args[0]] + args[2:], args[1]
        for spec in scan(roots, mode, task_name):
            if spec["id"] == fid:
                fig = render(spec)
                if fig is None:
                    break
                fig.savefig(sys.stdout, format="svg", facecolor="white")
                return
    sys.stderr.write("figure not found\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
