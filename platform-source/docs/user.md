# Molecular Dynamics Platform — User Guide

## Mindmap

```mermaid
mindmap
  root((MD Platform))
    Task Flow Pipeline
      Step 1
        seq_to_pdb
        Generate PDB with sequence
      Step 2
        tiger2
        Replica Exchange simulation
      Step 3
        tiger2 to CG
        DCD Conversion
      Step 4
        gromacs_cg
        CG Simulation for physical properties
      Symlink Chain
        Output to Input
        Ordered by creation time
    Monitoring Pages
      tiger2
        Convergence
          Block Analysis
          Equilibrium Check
        Temperature
          Exchange Events
          Layer Visits
          Scheduling
        Structure
          Annotated 3D Trajectory
          Video Export
          Rg E2E RMSD Monitoring
        Clustering
          K-means
          Scatter Plot
          Pie Chart
      gromacs_cg
        Structure
          Annotated 3D Trajectory
          Video Export
        Properties
          Physical properties calculation
    Task Control
      Start Stop Pause
      File Browser
      Task Creation
      Server Management
```

## Core Framework Status

### What You Have (Complete)

| Component | Status |
|-----------|--------|
| Task Pipeline (4 steps) | ✅ Complete |
| TIGER2 monitoring | ✅ Convergence, Temperature, Structure, Clustering |
| GROMACS CG monitoring | ✅ Structure, Properties |
| Transition tasks | ✅ seq_to_pdb, DCD→CG |
| Flow management | ✅ Symlink chain, sequential execution |
| Task control | ✅ CRUD, file browser, server management |
| Visualization | ✅ 3D viewer, video export, charts |

### Possible Extensions (Future)

| Feature | Priority | Notes |
|---------|----------|-------|
| Multi-run comparison | Medium | Compare multiple simulations side-by-side |
| Data export (CSV/JSON) | Low | For external analysis tools |
| Notification system | Low | Alert on completion/failure |
| GPU/resource monitoring | Low | Track compute usage |
| Batch job queue | Low | Manage multiple pending jobs |

**Your core framework is solid.** The pipeline covers the full MD workflow: structure preparation → simulation → analysis → coarse-graining. Monitoring pages match task capabilities. Extensions can be added incrementally as needed.
