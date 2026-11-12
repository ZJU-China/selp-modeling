# Task Structure & Quick-Create Channels

How a "task" is represented on disk, the two ways one gets created, and the
default templates that back the quick-create channel for each task type.

## 1. What a task actually is

A task is the union of two independent things that must agree on one `id`:

1. **An entry in `backend/tasks.json`** — `{ id, name, taskType, serverId,
   host, port, username, password|privateKey, workDir, config }`. This is
   connection/registry metadata: which server to SSH into, what to call the
   task, which tasktype's code drives it. Gitignored (holds credentials).
2. **A directory `backend/tasks/<id>/`** — `input/` (uploaded files, e.g.
   `sequences.csv`), `scripts/task_config.json` (task-specific parameters,
   see below), `logs/`, `cache/` (synced trajectory/analysis data), `output/`.

The backend never hardcodes per-task logic. Every request for task `<id>`
resolves its `taskType` from `tasks.json`, then calls
`getTaskScriptsDir(id, taskType)` (`backend/services/task-dir.js`), which
prefers the shared `backend/tasktype/<taskType>/` tree (falling back to
`<id>/scripts/` only for a task whose type has no shared tree). That shared
`main.py` then loads `backend/tasks/<id>/scripts/task_config.json` for
everything task-specific: remote paths, process-detection patterns, replica
counts, convergence thresholds, GROMACS sample globs, SLURM identifiers, etc.

Currently registered tasks (`backend/tasks.json`), by taskType:

| taskType | tasks | shared code |
|---|---|---|
| `tiger2` | `tiger2_legacy`, `tiger2_2ky5`, `tiger2_gpu`, `tiger2_zju` | `backend/tasktype/tiger2/` |
| `tiger2-convergence` | (UI-creatable; none registered yet) | alias of `tiger2` (`TASKTYPE_ALIASES` in `task-dir.js`) — same scripts, same template, just a different frontend nav/dashboard layout |
| `gromacs_cg` | `gromacs_cg_zju` | `backend/tasktype/gromacs_cg/` |
| `seq_to_pdb` | (transition task, created via flow pipeline) | `backend/tasktype/seq_to_pdb/` — local generation, no remote server |
| `tiger2_dcd_to_gromacs_cg_pdb` | (transition task, created via flow pipeline) | `backend/tasktype/tiger2_dcd_to_gromacs_cg_pdb/` — local generation, no remote server |

`task_config.json`'s shape is genuinely different per taskType (TIGER2 has
`convergence`/`monitor` blocks and NAMD process patterns; GROMACS CG has
`gromacs`/`slurm` blocks and `gmx` process patterns) — see each type's
`lib/task_config.py` for the authoritative field list.

## 2. Two ways to create a task — same contract, either way

**By hand** (how every task above was actually made): `mkdir -p
backend/tasks/<id>/{input,scripts,logs,cache}`, hand-write
`scripts/task_config.json`, add the connection entry to `tasks.json`.

**Quick-create channel** (`POST /api/tasks/create`, the frontend's "+ New
Task" button in Task Control): registers the `tasks.json` entry, then calls
`scaffoldTaskConfig(id, taskType, { remoteDir, logPrefix })`
(`backend/services/task-dir.js`), which:

- resolves `backend/tasktype/<taskType>/task_config.template.json` (falling
  back to an empty template if the type is unknown),
- fills in `remoteDir`/`logPrefix` from the form's Working Directory / Log
  Prefix fields,
- writes the result to `backend/tasks/<id>/scripts/task_config.json`,
- **never overwrites an existing file.**

That last point is the whole point: the quick-create channel and hand-authoring
target the exact same file at the exact same path, and neither path is ever
allowed to clobber the other. A task started by hand and later "created"
again through the API (e.g. a stale double-click) is a no-op on the config
file. A task scaffolded through the API can be freely hand-edited afterwards
— the scaffold is a one-time starting point, not a managed/generated file.
The same template is also reachable from Python
(`lib/task_config.py:write_default()`, used e.g. from an SSH session on the
compute host without going through the web UI) — one template file per
taskType, two callers, always in sync.

## 3. What quick-create can't know (and leaves as `FILL-IN`)

The templates (`backend/tasktype/<type>/task_config.template.json`) ship with
working defaults for anything generic (replica counts, process-detection
regexes, convergence thresholds) and an obvious `"FILL-IN: ..."` placeholder
string for anything that's genuinely per-task and unknowable at creation time:

- **tiger2**: `defaults.protein` (construct description shown on the
  Dashboard). `remoteDir`/`logPrefix` are filled from the create form when
  provided, `FILL-IN` otherwise.
- **gromacs_cg**: `defaults.protein`, `gromacs.sampleGlobs` (remote glob for
  the task's per-sample output dirs — every task's cluster layout differs),
  `slurm.user`/`slurm.jobPrefix`.

After quick-create, open `backend/tasks/<id>/scripts/task_config.json` and
replace every `FILL-IN: ...` string before starting the task — the create
form's success message names the exact path. Nothing reads the file until
the task is actually started/monitored, so this is safe to do at leisure.

## 4. Adding a new taskType's quick-create channel

1. Build the shared tree: `backend/tasktype/<type>/{main.py,lib/,routes/,
   gen_sim_status.py,analyze.py}` (see `tiger2/` or `gromacs_cg/` as a
   reference implementation of the `main.py route` dispatch pattern).
2. Add `backend/tasktype/<type>/task_config.template.json` — every field
   `lib/task_config.py` reads, with real defaults where generic and
   `"FILL-IN: ..."` where not.
3. (Optional, for CLI-side scaffolding) add a `write_default()` to
   `lib/task_config.py` that loads the template — copy the one in
   `tiger2/lib/task_config.py` or `gromacs_cg/lib/task_config.py` verbatim.
4. Add `{ id: "<type>", label: "..." }` to `TASK_TYPES` in
   `frontend/src/types.ts` so it appears in the create form's Task Type
   dropdown. Nothing else on the frontend needs to change — quick-create,
   the scaffolder, and `getTaskScriptsDir`'s dispatch are all taskType-generic.

## 5. Related

- [Sequence-annotation workflow](sequence-annotation-workflow.md) — another
  per-task input (`input/sequences.csv`) that's task-agnostic across all
  three types once `input/` exists, same "compatible regardless of how the
  task was created" property as `task_config.json`.

## 6. Annotation 数据传递

### 6.1 存储位置

Annotation 数据存储在任务的 `config.annotations` 字段中（`tasks.json` 的 `taskConfigs[].config.annotations`）。

格式：
```json
[
  {"label": "SnoopTag", "start": 1, "end": 12, "color": "#ff4d4f"},
  {"label": "Flexible linker", "start": 13, "end": 28, "color": "#52c41a"},
  ...
]
```

### 6.2 Flow 中的传递

Annotation 不会自动从上游任务传递到下游任务。每个任务需要独立配置 annotation。

推荐做法：
1. 在第一个任务（通常是 `seq_to_pdb`）中设置完整的 annotation
2. 通过 `PUT /api/tasks/update` 将相同的 annotation 复制到下游任务
3. 或在创建任务后手动编辑 `tasks.json`

### 6.3 Transition 任务的 Annotation

Transition 任务（`seq_to_pdb`、`tiger2_dcd_to_gromacs_cg_pdb`）的 annotation 主要用于前端 NGL.js 3D 查看器显示蛋白质结构区域。

`generate.py` 脚本不读取 annotation（annotation 仅影响前端显示），但 transition 任务的输出文件（如 `sequences.csv`）会包含 annotation 信息。
