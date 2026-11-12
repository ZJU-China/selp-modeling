"""Applied magnetic-field profiles along the sample axis.

A sample is a column of rubber of height ``height_m`` aligned with the applied
field.  Profiles supported:

* ``uniform``: constant magnitude H0 = max_t / mu0.
* ``gradient``: linear ramp from H0 to H0 + delta over the sample height.
* ``csv``: a table (x, y, z, H [A/m]) or (x, y, z, B [T]) sampled on the
  sample.  Position column ``z`` is used when present, else ``x``; multiple
  rows at the same position are averaged.  The profile is interpolated onto
  the sample grid.

CSV parsing is the exception to "positional column": it requires a header row
whose cells map column names (lower-cased) to roles, e.g.
``x,y,z,H`` or ``x,y,z,B``.
"""
import csv
import math
from bisect import bisect_left

MU0 = 4.0 * math.pi * 1e-7

DEFAULT_HEIGHT_M = 0.01  # 10 mm
DEFAULT_N_POINTS = 201


def _h0_from_max_t(max_t):
    return max_t / MU0


def grid_count(points):
    return max(2, int(points))


def build_grid(height_m=DEFAULT_HEIGHT_M, n_points=DEFAULT_N_POINTS):
    n = grid_count(n_points)
    return [height_m * i / (n - 1) for i in range(n)]


def uniform_profile(height_m=DEFAULT_HEIGHT_M, n_points=DEFAULT_N_POINTS, max_t=0.6):
    h0 = _h0_from_max_t(max_t)
    return [[z, h0] for z in build_grid(height_m, n_points)]


def gradient_profile(height_m=DEFAULT_HEIGHT_M, n_points=DEFAULT_N_POINTS,
                     max_t=0.6, delta_t=0.2):
    zs = build_grid(height_m, n_points)
    h0 = _h0_from_max_t(max_t)
    dh = delta_t / MU0
    return [[z, h0 + dh * (z / height_m if height_m > 0 else 0.0)] for z in zs]


def _position_role(roles):
    """Resolve the position column to (index, scale-to-metres).

    An explicit unit suffix wins: ``z_mm``/``x_mm`` is millimetres and
    ``z_m``/``x_m`` is metres. A bare ``z``/``x`` stays metres, which is what
    this loader has always assumed. The suffix matters because the panel
    collects the sample height in millimetres, so a profile exported in the same
    units would otherwise be read as 1000x too large and clamp to a flat field.
    """
    for name in ("z_mm", "x_mm", "position_mm"):
        if name in roles:
            return roles[name], 1e-3
    for name in ("z_m", "x_m", "position_m"):
        if name in roles:
            return roles[name], 1.0
    for name in ("z", "x", "position"):
        if name in roles:
            return roles[name], 1.0
    return None


def load_csv_profile(path, height_m=DEFAULT_HEIGHT_M, n_points=DEFAULT_N_POINTS):
    """Load a field CSV and interpolate onto the sample grid -> [[z, H], ...].

    Position columns: ``z``/``x`` (metres), or the explicit ``z_mm``/``x_mm``.
    Field columns: ``b`` (tesla) or ``h`` (A/m).
    """
    rows = []
    roles = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            cells = [c.strip() for c in row if c.strip()]
            if not cells:
                continue
            if i == 0:
                for c in cells:
                    roles[c.lower()] = len(roles)  # preserve first-occurrence index
                continue
            if len(cells) < len(roles):
                continue
            pos_role = _position_role(roles)
            if pos_role is None:
                continue
            idx, scale = pos_role
            try:
                pos = float(cells[idx]) * scale
                if "b" in roles:
                    h = float(cells[roles["b"]]) / MU0
                elif "h" in roles:
                    h = float(cells[roles["h"]])
                else:
                    continue
            except (ValueError, IndexError):
                continue
            rows.append((pos, h))
    if not rows:
        raise ValueError("no usable field rows in %s (expected header with x,y,z,H or x,y,z,B)" % path)

    rows.sort(key=lambda r: r[0])
    zs = build_grid(height_m, n_points)
    # Interpolation clamps to the ends, so a file whose positions do not match
    # the sample silently yields a wrong field: one that stops short reads as a
    # flat extension of its nearest end, and one that spans far beyond it
    # contributes only the rows near the origin. The second is what millimetres
    # read as metres looks like, and the panel collects height in millimetres.
    lo, hi = rows[0][0], rows[-1][0]
    tol = max(1e-12, abs(height_m) * 1e-3)
    if lo > height_m + tol or hi < height_m - tol:
        raise ValueError(
            "field file positions span %.6g..%.6g m, which does not cover the sample "
            "(0..%.6g m); a profile from another origin cannot be used here"
            % (lo, hi, height_m)
        )
    if hi > abs(height_m) * 100.0:
        raise ValueError(
            "field file positions span %.6g..%.6g m but the sample is %.6g m tall; "
            "if these are millimetres, rename the column to z_mm" % (lo, hi, height_m)
        )
    out = []
    for z in zs:
        vals = [h for (p, h) in rows if p == z]
        if vals:
            out.append([z, sum(vals) / len(vals)])
            continue
        pos = [r[0] for r in rows]
        hs = [r[1] for r in rows]
        idx = bisect_left(pos, z)
        if idx == 0:
            out.append([z, hs[0]])
        elif idx >= len(pos):
            out.append([z, hs[-1]])
        else:
            t = (z - pos[idx - 1]) / (pos[idx] - pos[idx - 1])
            out.append([z, hs[idx - 1] * (1 - t) + hs[idx] * t])
    return out


def make_profile(mode, params):
    """Dispatch a profile config dict -> [[z_m, H_app(A/m)], ...]."""
    height = float(params.get("heightM") or params.get("heightMm", 0)) / 1e3 if params.get("heightM") else \
        float(params.get("heightMm", DEFAULT_HEIGHT_M * 1e3)) / 1e3
    n = int(params.get("nPoints", DEFAULT_N_POINTS))
    mode = (mode or "uniform").lower()
    if mode == "gradient":
        return gradient_profile(height, n,
                                max_t=float(params.get("maxT", 0.6)),
                                delta_t=float(params.get("gradientDeltaT", 0.2)))
    if mode == "csv":
        return load_csv_profile(params["csvPath"], height, n)
    return uniform_profile(height, n, max_t=float(params.get("maxT", 0.6)))