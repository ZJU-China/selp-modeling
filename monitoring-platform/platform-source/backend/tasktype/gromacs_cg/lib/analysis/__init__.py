"""Offline analysis package for GROMACS (coarse-grained) tasks.

Modules are imported on demand by the task's `analyze.py` orchestrator; each
module is self-contained and reports success/failure independently so a missing
artifact (no DCD, no EDR, no network.json) only disables that feature:

  paths       - local task path + task_config resolution
  writers     - .dat / .tsv / .json output helpers
  structure   - radii of gyration, end-to-end, RMSD, per-chain Rg, box size
  energies    - per-step energy / temperature series from relax.edr (gmx energy)
  network     - crosslink distances + per-link stats from network.json layout
  modulus     - rubber elasticity of the task's own network.json (network32)
"""