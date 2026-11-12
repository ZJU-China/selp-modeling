# Standardized Sequence-Annotation Workflow

Annotate peptide motifs (SnoopTag, flexible linkers, ...) directly on the
MD-trajectory structure viewer. Motifs are declared once as a CSV in the
task's `input/` dir; the backend finds **every** residue-range occurrence in
the topology and the frontend highlights them all.

## 1. CSV schema — `input/sequences.csv`

Place a CSV named `sequences.csv` in the task's input directory
(`backend/tasks/<taskId>/input/`). One motif per line, header required:

```csv
sequence,label,color
KLGYIEFYKVEK,SnoopTag,#ff4d4f
GGGGS,Flexible linker peptide,#52c41a
```

| column     | meaning                                                          |
|------------|------------------------------------------------------------------|
| `sequence` | 1-letter amino-acid code of the motif, uppercase (e.g. `KLGYIEFYKVEK`) |
| `label`    | display name shown in the viewer legend                          |
| `color`    | hex colour (`#rrggbb`) used to highlight every occurrence        |

Colors: each distinct sequence is highlighted in its own color. When a row
omits `color` (or repeats an already-used one), the backend auto-assigns the
next free colour from a fixed distinct palette — so different sequences are
always visually distinguishable even without manual hex codes.

Notes:

- The CSV is uploaded to the remote host alongside the other `input/` files;
  it is harmless to the simulation.
- `backend/tasks/*/input/` is git-ignored (runtime data), so commit new CSVs
  with `git add -f backend/tasks/<taskId>/input/sequences.csv` so they deploy
  through the normal push + `git reset --hard origin/master` flow.

## 2. Backend — occurrence computation

- `backend/tasktype/tiger2/lib/sequence_annotation.py` reads the CSV, loads
  the structure (`cache/trajectory/topology.pdb`, else the first
  `input/*.pdb`) and matches each motif as a contiguous 1-letter sequence per
  chain (including overlapping hits). It returns JSON:

  ```json
  {
    "ok": true,
    "csv": "sequences.csv",
    "pdb": "topology.pdb",
    "chains": ["A"],
    "totalResidues": 564,
    "annotations": [
      { "sequence": "KLGYIEFYKVEK", "label": "SnoopTag", "color": "#ff4d4f",
        "occurrences": [
          { "chain": "A", "start": 1, "end": 12, "atomStart": 1, "atomEnd": 221 },
          { "chain": "A", "start": 553, "end": 564, "atomStart": 6496, "atomEnd": 6715 }
        ] }
    ]
  }
  ```

- Exposed via `GET /api/data/sequence-annotations?taskId=<taskId>` (route
  `sequences` in `backend/tasktype/<taskType>/routes/`), computed locally with
  no SSH round-trip. Missing CSV or structure degrades to `{ annotations: [] }`.
- The matching logic (`lib/sequence_annotation.py`) is duplicated per tasktype
  (same convention as `lib/ssh_client.py` etc.) rather than shared, so it
  works unmodified for `tiger2`, `tiger2-convergence` (alias of `tiger2`) and
  `gromacs_cg` alike: it only depends on standard PDB `ATOM`/`HETATM` records
  (`chain`, `resname`, `resid`), grouping multiple lines with the same `resid`
  into one residue — which is what a coarse-grained (Martini) topology looks
  like too (several beads, e.g. `BB`/`SC1`/`SC2`, sharing one resname/resid).
  One CG-specific caveat: MDAnalysis writes `topology.pdb` from a `.gro` with
  no chain IDs, so a multi-chain CG system collapses to a single chain in the
  PDB — occurrences still resolve correctly by residue range, they just won't
  carry a real per-chain `chain` label.

## 3. Frontend — MD-trajectory highlighting

`frontend/src/components/MolecularViewer.tsx` fetches the annotations on
mount, then for each motif adds one NGL `cartoon` representation (recolors the
backbone of all occurrences) and one `spacefill` representation (marker
spheres), both coloured with the CSV colour and restricted to **all**
occurrences. The unannotated protein keeps a neutral base cartoon (white in
dark mode, light grey in light mode).

Selection strings use NGL's compact `resno:chain` form, e.g.
`1-12:A or 553-564:A`. The bundled NGL build does **not** understand the
keyword syntax (`chain A and resid 1-12`): the parse silently fails and the
representation then selects *every* atom, painting the whole molecule in the
last colour added. Verify any new selection form against the structure before
using it.
Selections are structure-based so they persist across playback frames and
every representation mode. The header legend lists each motif with its colour
and occurrence count; the Residues stat card shows the topology's real
residue count (`totalResidues`).

## 4. Extending the workflow

- **New motif**: add a line to `input/sequences.csv` → backend + viewer pick
  it up automatically on the next page load.
- **Another task**: copy the CSV into that task's `input/` dir. The workflow
  is task-agnostic (works for `tiger2`, `tiger2-convergence` and `gromacs_cg`
  tasks) — e.g. the 2KY10-SnoopTag CSV (`sequences.csv` above) is reused as-is
  for `tiger2_2ky5` (2KY5-SnoopyTag) and `gromacs_cg_zju` (2KY10 CG network):
  same SnoopTag/linker motifs, same underlying amino-acid sequence, different
  simulation method.
- **Different colour scheme / representation**: change `color` in the CSV or
  the `spacefill` representation parameters in `applyAnnotations()`.
- **Chain-aware**: occurrences already carry `chain`; selections use the
  compact `resno:chain` form (`1-12:A`), and empty chain selects `resno`
  alone, so multi-chain topologies are handled per chain.
