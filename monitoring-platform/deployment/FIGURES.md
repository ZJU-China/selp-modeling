# SELP Modeling — flows, tasks and figures

This note documents how the Flow Console pages under `/flows.html` produce their
charts: which files are metadata, how the plotting script is chosen, and what each
figure means. No rendered image is ever used as a data source.

## 1. Project shape

- `/home/selp/Repository/selp-web` — static site (Apple-style landing page) plus
  the embedded Flow Console (`/flows/app/`) and the deployment tooling.
- `/home/selp/igem-2026/igem-2026-software` — the real platform: Express backend
  (port 3001), React Flow Console, and the task-type runners (TIGER2, GROMACS CG,
  magnetomech).
- `/home/selp/selp-figures/render_task.py` — the compatibility renderer used by
  `/api/tasks/:id/figures`; it classifies metadata files, merges time segments,
  and draws SVG charts with labelled axes.

## 2. Flows and tasks

Each construct (2KY-5, 2KY-10, 2KY-16) is one flow with three steps:

1. **TIGER2 sampling** (`tiger2`) — NAMD replica-exchange sampling; logs are the
   metadata (`production/*/*.log`, `logs/*/*.log`).
2. **GROMACS CG network** (`gromacs_cg`) — coarse-grained network run; metadata
   is `*.xvg` (thermo, distances) plus optional CSVs.
3. **Magnetomech / mechanics** (`magnetomech`) — local field-deformation model;
   metadata is the calibration/result CSV/JSON and the pull-run `.xvg` files.

The transition step (`tiger2_dcd_to_gromacs_cg_pdb`) is folded into the task
graph: the CG task depends directly on the TIGER2 task.

## 3. Figure semantics

| Task type | Metadata | Figure title | Axes |
| --- | --- | --- | --- |
| TIGER2 | NAMD `.log` ENERGY records | **Total energy**, **Temperature** | x = step; y = kcal/mol or K; one line per replica |
| GROMACS CG | `distances.xvg` | **Network distances** | x = time/step; y = distance (mean of columns) |
| GROMACS CG | `thermo.xvg` | **Temperature** | x = time/step; y = temperature column |
| GROMACS CG | other `.xvg` | title from metric (e.g. Pull force) | x = time/step; y = column mean |
| Mechanics | calibration CSV/JSON | **Empirical modulus (kPa)** etc. | x = category; y = value |
| Mechanics | pull `.xvg` | **Pull force**, **Pull x** | x = time/step; y = pull value |
| Any | results JSON with `rows` | title from quantity | bar chart, x = branch |

### Merge rule

Files that differ only by a time/segment number are one measurement chopped along
time: `relax1500/relax2000/...`, `continue_300/325/...`, `part0003/part0004/...`.
The renderer normalises numbers of 3+ digits to `#`, concatenates the series per
replica/branch, deduplicates repeated steps, and draws them as **one** chart:

- TIGER2: logs for replica *r* are concatenated by step; replicas become separate
  lines in the same "Total energy" / "Temperature" chart.
- CG/mechanics: segments of the same branch are concatenated; different branches
  become separate lines.

Figures whose function is already covered by a native platform chart are not
listed again: `analysis/thermo.csv` (Structure/Convergence tabs) and
`magnetomech.curve.csv` / `magnetomech.layer.csv` (native magnetomech panel).

## 4. Reference tab

Each flow page has a **Reference** tab. It calls `/api/tasks/:id/figures` and lists,
per step: figure title, format, the metadata file(s) (merged figures show every
segment), and the plotting script (`figures-service/render_task.py`).

## 5. API

- `GET /api/tasks/:id/figures` — list of figure specs (id, title, kind, path,
  sources, script).
- `GET /api/tasks/:id/figures/:id.svg` — render one chart from metadata on demand
  (no stored image).

## 6. Known limits

- Axis values come from the files as written by the simulations; no unit
  conversion is applied.
- 2KY-16 E2E steered MD (`2KY16_E2E10nm_20261105`) runs independently of the
  three-step flows and is not yet a task there.
- The renderer reads log/xvg/csv/json only; trajectories/structures are handled by
  the native Structure/Convergence tabs, not by these figures.
