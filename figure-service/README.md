# SELP figure service

Renders the site's data figures from the actual task files on the iGEM server, so a
figure always reflects the data product it is drawn from instead of a frozen PNG.

## Run

```bash
/home/selp/venvs/wjx/bin/python server.py
# GET http://127.0.0.1:8766/charts/<chart>.svg?task=joint
```

nginx on the site (port 8765) proxies `/charts/` to this service.

## Charts and their sources (task `joint`)

| chart id | data product |
| --- | --- |
| `calibration` | `transparent_figure_set_20261015/native_calibration/source_parameters_and_results.json` |
| `md-controls` | `md_supplement_figures_20261013/block_means_20ps.json` |
| `famd-metrics` | `methods_documentation_20261101/data/FAMD_2KY10_baseline_metrics.csv` |
| `rmsd` | same CSV, RMSD column |
| `em` | `EM_2KY5_potential.csv`, `EM_2KY10_segment_end_force.csv` |
| `nvt` | `NVT10_thermo.csv`, `NVT10_potential.csv` |
| `npt` | `NPT100_thermo.csv`, `NPT100_potential.csv` |
| `step-min` | `SELP_methods_FAMD_details_20261102/data/01,02_*.csv` |
| `step-warm` | `03_gbis_warm_025fs.csv` |
| `step-prep` | `04..07_gbis_eq_*.csv` |

Add a new task in `tasks.json` (same keys, different files) and call
`/charts/<id>.svg?task=<name>`.

## Still static

Molecular renders (fig13, figS4, F07, F09), schematics (fig01, fig02, fig07, fig12,
fig16, fig_unlinked) and the contact-evidence panel (fig15) keep their exported
images; their inputs are structures/snapshots rather than tabular series.

The public snapshot starts with an empty `tasks.json`. Add local task data paths to enable chart rendering.
