import { join } from "path"
import { existsSync, readFileSync, readdirSync } from "fs"
import { getTaskBaseDir, getTaskCacheDir, getTaskOutputDir, getTaskInputDir } from "./task-dir.js"
import { buildEditablePanel } from "./editable-params.js"
import { TRANSITION_TASK_TYPES, LOCAL_TASK_TYPES } from "../store.js"
import { buildExecution } from "./task-execution.js"

// ---------------------------------------------------------------------------
// Flow overview: one aggregated payload describing an entire flow.
//
// The dashboard is flow-centric (one page per flow), but the backend still
// stores everything per task, and each tasktype reports status in its own
// shape. Rather than have the UI learn five status dialects and fan out 4xN
// requests, this module normalises once, here.
//
// Nothing in this file mutates state. It reads the on-disk artefacts the
// compute/analysis steps already write, so it stays correct whether or not a
// remote host is currently reachable.
// ---------------------------------------------------------------------------

export const TASK_STATE = {
  PENDING: "PENDING",
  RUNNING: "RUNNING",
  DONE: "DONE",
  FAILED: "FAILED",
}

function readJson(path) {
  try { return JSON.parse(readFileSync(path, "utf8")) } catch { return null }
}

function dirHasFiles(dir) {
  try { return readdirSync(dir).some(n => !n.startsWith(".")) } catch { return false }
}

export function getSimStatus(taskId) {
  // Prefer the task's own cache copy; it is refreshed by the sim-status sync
  // and is the only variant that works without SSH.
  return readJson(join(getTaskCacheDir(taskId), "sim_status.json"))
}

export function getMagnetomechConfig(taskId) {
  return readJson(join(getTaskCacheDir(taskId), "magnetomech", "config.json"))
}

export function getMagnetomechSummary(taskId) {
  return readJson(join(getTaskCacheDir(taskId), "magnetomech", "magnetomech.summary.json"))
}

// Parse the motif table used for structure annotation.
//
// Format (input/sequences.csv):
//   sequence,label,color
//   KLGYIEFYKVEK,SnoopTag,#ff4d4f
//
// This is the *input* side. It is distinct from the resolved occurrences the
// viewer consumes (/api/data/sequence-annotations, which matches motifs against
// the topology and returns concrete residue ranges) — the flow pages show the
// input table, and treat resolved occurrences as a separate concern.
export function readSequenceAnnotations(taskId) {
  const csv = join(getTaskInputDir(taskId), "sequences.csv")
  if (!existsSync(csv)) {
    return {
      present: false,
      reason: "No sequences.csv in the task input directory",
      path: "input/sequences.csv",
      motifs: [],
    }
  }
  let raw = ""
  try { raw = readFileSync(csv, "utf8") } catch (e) {
    return { present: false, reason: `Unreadable: ${e.message}`, path: "input/sequences.csv", motifs: [] }
  }
  const lines = raw.split(/\r?\n/).filter(l => l.trim() && !l.trim().startsWith("#"))
  const motifs = []
  for (const line of lines.slice(1)) {           // line 0 is the header
    const [sequence, label, color] = line.split(",").map(s => s.trim())
    if (!sequence) continue
    motifs.push({ sequence, label: label || sequence, color: color || "" })
  }
  return {
    present: true,
    path: "input/sequences.csv",
    header: lines[0] || "sequence,label,color",
    count: motifs.length,
    motifs,
  }
}

// ---------------------------------------------------------------------------
// Crosslink degree (GROMACS CG)
//
// Honest answer: the backend has no crosslink parameter and no task in this
// deployment carries crosslink artefacts. Crosslinking is a fixed property of
// the prepared CG topology (network.json / crosslink_pairs.tsv, generated
// offline by CG/generate_32chain_candidates.py), not a runtime knob -- the only
// place the number is currently expressed is `--n-crosslinks` on
// scripts/cg_autopilot.py.
//
// So: report the analysis artefacts when they exist, otherwise say so plainly
// rather than inventing a number.
// ---------------------------------------------------------------------------
const CROSSLINK_ARTEFACTS = [
  { file: "crosslink.dat", kind: "series" },
  { file: "crosslink_table.tsv", kind: "table" },
]

export function readCrosslink(taskId) {
  const roots = [getTaskCacheDir(taskId), getTaskOutputDir(taskId)]
  const found = []
  for (const root of roots) {
    for (const a of CROSSLINK_ARTEFACTS) {
      const p = join(root, "analysis", a.file)
      if (existsSync(p)) found.push({ ...a, path: p })
      const p2 = join(root, a.file)
      if (existsSync(p2)) found.push({ ...a, path: p2 })
    }
  }
  if (found.length === 0) {
    return {
      available: false,
      reason: "Crosslinking is a fixed property of the prepared CG topology, not a " +
              "per-task backend parameter. No crosslink.dat / crosslink_table.tsv " +
              "artefact was produced for this task.",
      source: "CG/generate_32chain_candidates.py -> network.json, crosslink_pairs.tsv",
      tunableVia: "scripts/cg_autopilot.py --n-crosslinks (default 44)",
    }
  }
  return { available: true, artefacts: found.map(f => ({ kind: f.kind, path: f.path })) }
}

// ---------------------------------------------------------------------------
// Which result artefacts exist for a task, so the UI can group the
// visualisation cards instead of rendering empty panels.
// ---------------------------------------------------------------------------
const STRUCTURE_SERIES = [
  { key: "rg", file: "rg.dat", label: "Radius of gyration", unit: "A" },
  { key: "e2e", file: "e2e.dat", label: "End-to-end distance", unit: "A" },
  { key: "rmsd", file: "rmsd.dat", label: "RMSD", unit: "A" },
  { key: "ss", file: "ss.dat", label: "Secondary structure", unit: "%" },
  { key: "energy", file: "energy.dat", label: "Energy", unit: "kJ/mol" },
  { key: "box", file: "box.dat", label: "Box vectors", unit: "nm" },
  { key: "chainRg", file: "chain_rg.dat", label: "Per-chain Rg", unit: "A" },
  { key: "crosslink", file: "crosslink.dat", label: "Crosslinks", unit: "count" },
]

export function readArtifacts(taskId) {
  const analysis = join(getTaskCacheDir(taskId), "analysis")
  const series = []
  for (const s of STRUCTURE_SERIES) {
    if (existsSync(join(analysis, s.file))) {
      series.push({ key: s.key, label: s.label, unit: s.unit })
    }
  }
  const has = p => existsSync(p)
  const trajectoryDir = join(getTaskCacheDir(taskId), "trajectory")
  let trajectory = null
  if (has(trajectoryDir)) {
    try {
      const files = readdirSync(trajectoryDir)
      const dcd = files.filter(f => f.endsWith(".dcd"))
      const pdb = files.filter(f => f.endsWith(".pdb"))
      if (dcd.length || pdb.length) {
        trajectory = { frames: dcd, topology: pdb, source: "cache/trajectory" }
      }
    } catch {}
  }
  const status = getSimStatus(taskId)
  return {
    structure: series,
    meta: has(join(analysis, "meta.json")) ? readJson(join(analysis, "meta.json")) : null,
    trajectory,
    magnetomech: has(join(getTaskCacheDir(taskId), "magnetomech", "magnetomech.summary.json")),
    magnetomechImage: has(join(getTaskCacheDir(taskId), "magnetomech", "final_simulation.png")),
    convergence: has(join(getTaskCacheDir(taskId), "_convergence_state.json")),
    temperature: Object.keys(status?.temp_visit_counts || {}).length > 0,
  }
}

// ---------------------------------------------------------------------------
// Status normalisation
// ---------------------------------------------------------------------------
export function normalizeStatus(task) {
  const { id, taskType } = task

  // Transition steps are local file generators: they either produced their
  // output dir or they have not run yet.
  if (TRANSITION_TASK_TYPES.has(taskType)) {
    const out = getTaskOutputDir(id)
    const produced = dirHasFiles(out)
    return {
      state: produced ? TASK_STATE.DONE : TASK_STATE.PENDING,
      progressPct: produced ? 100 : 0,
      detail: produced
        ? `Generated ${readdirSync(out).filter(n => !n.startsWith(".")).length} output item(s)`
        : "Awaiting upstream output",
      evidence: "output directory contents",
    }
  }

  const status = getSimStatus(id)

  // magnetomech runs locally to completion in one shot and reports
  // running:false by construction (gen_sim_status.py is a benign stub — "a
  // magnetomech task never runs a simulation"). Its real state is whether the
  // summary artefact exists.
  if (LOCAL_TASK_TYPES.has(taskType)) {
    const summary = getMagnetomechSummary(id)
    if (summary) {
      return {
        state: TASK_STATE.DONE,
        progressPct: 100,
        detail: "Result computed locally",
        evidence: "cache/magnetomech/magnetomech.summary.json",
      }
    }
    return {
      state: TASK_STATE.PENDING,
      progressPct: 0,
      detail: "Not yet computed",
      evidence: "cache/magnetomech/ absent",
    }
  }

  const overall = status?.overall || {}
  const running = !!overall.running
  const pct = Number(overall.avg_progress_pct)
  const hasProgress = Number.isFinite(pct) && pct > 0

  if (running) {
    return {
      state: TASK_STATE.RUNNING,
      progressPct: Number.isFinite(pct) ? pct : 0,
      detail: hasProgress ? `${pct.toFixed(1)}% complete` : "Running",
      evidence: "sim_status.overall.running",
    }
  }

  // Not running. A task that has produced samples/artefacts but sits below
  // 100% has either finished or stalled; the guard events are what separate
  // the two, and that judgement belongs to services/task-guard.js.
  const artifacts = readArtifacts(id)
  const producedSomething = artifacts.structure.length > 0 || !!artifacts.trajectory
  if (Number.isFinite(pct) && pct >= 100) {
    return { state: TASK_STATE.DONE, progressPct: 100, detail: "Reached target", evidence: "sim_status.overall.avg_progress_pct" }
  }
  if (hasProgress) {
    return {
      state: TASK_STATE.PENDING,
      progressPct: pct,
      detail: `Not running · last reported ${pct.toFixed(1)}%`,
      evidence: "sim_status.overall.avg_progress_pct",
    }
  }
  if (producedSomething) {
    return {
      state: TASK_STATE.DONE,
      progressPct: 100,
      detail: "Result artefacts present",
      evidence: "cache/analysis",
    }
  }
  return {
    state: TASK_STATE.PENDING,
    progressPct: 0,
    detail: "No run data yet",
    evidence: "sim_status absent or zeroed",
  }
}

// ---------------------------------------------------------------------------
// Parameter panels, grouped by the task type the user asked about.
// ---------------------------------------------------------------------------
function tiger2Params(task) {
  const annotations = readSequenceAnnotations(task.id)
  const cfg = getSimStatus(task.id)?.config || {}
  return {
    panel: "tiger2",
    title: "Input sequence & annotation table",
    fields: [
      { key: "protein", label: "Protein", value: cfg.protein || cfg.proteinName || null },
      { key: "forceField", label: "Force field", value: cfg.force_field || null },
      { key: "numReplicas", label: "Replicas", value: cfg.num_replicas ?? null },
      { key: "stepsPerCycle", label: "Steps / cycle", value: cfg.steps_per_cycle ?? null },
      { key: "totalCycles", label: "Target cycles", value: cfg.total_cycles ?? null },
    ],
    annotations,
  }
}

// flow_tiger2 folds seq-to-PDB into the TIGER2 task, so its Parameters panel is
function gromacsCgParams(task) {
  const cfg = getSimStatus(task.id)?.config || {}
  return {
    panel: "gromacs_cg",
    title: "Crosslink degree",
    fields: [
      { key: "forceField", label: "Force field", value: cfg.force_field || null },
      { key: "numReplicas", label: "Replicas", value: cfg.num_replicas ?? null },
      { key: "plannedNs", label: "Planned length", value: cfg.total_cycles ?? null, suffix: "ns" },
    ],
    crosslink: readCrosslink(task.id),
  }
}

function magnetomechParams(task) {
  const cfg = getMagnetomechConfig(task.id) || {}
  const field = cfg.field || {}
  const particle = cfg.particle || {}
  return {
    panel: "magnetomech",
    title: "Applied magnetic field",
    fields: [
      { key: "fieldMode", label: "Field mode", value: field.mode ?? null },
      { key: "maxT", label: "Base field", value: field.maxT ?? null, suffix: "T" },
      { key: "gradientDeltaT", label: "Field rise", value: field.gradientDeltaT ?? null, suffix: "T" },
      { key: "heightMm", label: "Sample height", value: field.heightMm ?? null, suffix: "mm" },
      { key: "nPoints", label: "Profile points", value: field.nPoints ?? null },
      { key: "temperatureK", label: "Temperature", value: cfg.temperatureK ?? null, suffix: "K" },
      { key: "phi", label: "Particle volume fraction", value: particle.phi ?? null },
      { key: "modulusMode", label: "Modulus mode", value: cfg.modulusMode ?? null },
    ],
    // "Input magnetic field file" only exists for field.mode === "csv".
    // For uniform/gradient the field is generated, not read from a file, so
    // the panel reports that rather than showing an empty file slot.
    fieldFile: {
      mode: field.mode ?? null,
      csvPath: field.csvPath ?? null,
      applicable: field.mode === "csv",
      reason: field.mode === "csv"
        ? null
        : `Field mode is "${field.mode ?? "unset"}" — the profile is generated from the parameters above, not read from a CSV file.`,
    },
  }
}

function transitionParams(task) {
  const cfg = readJson(join(getTaskBaseDir(task.id), "scripts", "task_config.json")) || {}
  return {
    panel: "transition",
    title: "Transition parameters",
    fields: [
      { key: "temperatureC", label: "Temperature", value: cfg.temperatureC ?? null, suffix: "°C" },
      { key: "sourceTaskId", label: "Upstream task", value: cfg.sourceTaskId ?? null },
    ],
  }
}

export function buildParamsPanel(task) {
  // A task type listed in services/editable-params.js renders as an input form
  // instead of a read-only summary: the user fills in the fields, saves, and
  // restarts, and the task type re-derives its inputs from them on every start.
  // Adding a type there is the only step needed to make its panel editable.
  const editable = buildEditablePanel(task)
  if (editable) return editable
  switch (task.taskType) {
    case "tiger2":
    case "tiger2-convergence":
      return tiger2Params(task)
    case "gromacs_cg":
      return gromacsCgParams(task)
    case "magnetomech":
      return magnetomechParams(task)
    default:
      return transitionParams(task)
  }
}

// Which interactive controls make sense for this task type.
export function buildControls(task) {
  const type = task.taskType
  if (type === "tiger2" || type === "tiger2-convergence") {
    return [
      { id: "start", label: "Start", kind: "run", endpoint: `/api/tasks/${task.id}/start` },
      { id: "stop", label: "Stop", kind: "run", endpoint: `/api/tasks/${task.id}/stop` },
      { id: "restart", label: "Restart", kind: "run", endpoint: `/api/tasks/${task.id}/restart` },
      { id: "pause", label: "Pause", kind: "run", endpoint: `/api/tasks/${task.id}/pause` },
      { id: "continue", label: "Continue", kind: "run", endpoint: `/api/tasks/${task.id}/continue` },
      { id: "temperature", label: "Temperature", kind: "view", view: "temperature" },
      { id: "convergence", label: "Convergence", kind: "view", view: "convergence" },
      { id: "structure", label: "Structure", kind: "view", view: "structure" },
    ]
  }
  if (type === "flow_tiger2") {
    // Same MD surface as tiger2 -- the difference is upstream, in the
    // structure synthesis that start/restart performs first.
    return [
      { id: "start", label: "Start", kind: "run", endpoint: `/api/tasks/${task.id}/start` },
      { id: "stop", label: "Stop", kind: "run", endpoint: `/api/tasks/${task.id}/stop` },
      { id: "restart", label: "Restart", kind: "run", endpoint: `/api/tasks/${task.id}/restart` },
      { id: "pause", label: "Pause", kind: "run", endpoint: `/api/tasks/${task.id}/pause` },
      { id: "continue", label: "Continue", kind: "run", endpoint: `/api/tasks/${task.id}/continue` },
      { id: "temperature", label: "Temperature", kind: "view", view: "temperature" },
      { id: "convergence", label: "Convergence", kind: "view", view: "convergence" },
      { id: "structure", label: "Structure", kind: "view", view: "structure" },
    ]
  }
  if (type === "flow_gromacs_cg") {
    // Same CG surface as gromacs_cg -- the difference is upstream, in the run
    // inputs that start/restart regenerate from the Parameters panel first.
    return [
      { id: "start", label: "Start", kind: "run", endpoint: `/api/tasks/${task.id}/start` },
      { id: "stop", label: "Stop", kind: "run", endpoint: `/api/tasks/${task.id}/stop` },
      { id: "restart", label: "Restart", kind: "run", endpoint: `/api/tasks/${task.id}/restart` },
      { id: "pause", label: "Pause", kind: "run", endpoint: `/api/tasks/${task.id}/pause` },
      { id: "continue", label: "Continue", kind: "run", endpoint: `/api/tasks/${task.id}/continue` },
      { id: "structure", label: "Structure", kind: "view", view: "structure" },
    ]
  }
  if (type === "gromacs_cg") {
    return [
      { id: "start", label: "Start", kind: "run", endpoint: `/api/tasks/${task.id}/start` },
      { id: "stop", label: "Stop", kind: "run", endpoint: `/api/tasks/${task.id}/stop` },
      { id: "restart", label: "Restart", kind: "run", endpoint: `/api/tasks/${task.id}/restart` },
      { id: "pause", label: "Pause", kind: "run", endpoint: `/api/tasks/${task.id}/pause` },
      { id: "continue", label: "Continue", kind: "run", endpoint: `/api/tasks/${task.id}/continue` },
      { id: "structure", label: "Structure", kind: "view", view: "structure" },
    ]
  }
  if (type === "magnetomech" || type === "flow_magnetomech") {
    // Same surface as magnetomech. flow_magnetomech re-derives the composite
    // fractions and the field profile from the panel before computing, so an
    // edited value is not shadowed by a stale input file.
    return [
      { id: "run", label: "Compute", kind: "run", endpoint: `/api/data/magnetomech/run?taskId=${task.id}`, method: "POST" },
      { id: "fielddeformation", label: "Field deformation", kind: "view", view: "field-deformation" },
    ]
  }
  return [
    { id: "start", label: "Generate", kind: "run", endpoint: `/api/transition/generate`, method: "POST" },
  ]
}

// ---------------------------------------------------------------------------
// The aggregate payload
// ---------------------------------------------------------------------------
export async function buildFlowOverview(flow, tasks) {
  // Async because each step resolves its real execution environment (SSH host,
  // data paths, gmx/matlab commands). That is what makes the panel able to
  // state where a step runs instead of leaving the user to read tasks.json.
  const steps = await Promise.all(tasks.map(async (task, index) => {
    const status = normalizeStatus(task)
    const artifacts = readArtifacts(task.id)
    return {
      index,
      id: task.id,
      name: task.name,
      taskType: task.taskType,
      isTransition: TRANSITION_TASK_TYPES.has(task.taskType),
      isLocal: LOCAL_TASK_TYPES.has(task.taskType),
      status,
      params: buildParamsPanel(task),
      artifacts,
      controls: buildControls(task),
      workDir: task.workDir || null,
      execution: await buildExecution(task),
    }
  }))

  // Two different questions, which are not the same question:
  //
  //   reachedIndex  the furthest step that has started work  -> how far the
  //                 bar should extend
  //   currentIndex  the first step that is not finished      -> where work is
  //                 happening right now
  //
  // They diverge whenever a later step completes while an earlier one is still
  // running (a restarted smoke step under an already-finished pipeline). Then
  // currentIndex points *backwards* from reachedIndex, so reporting only one of
  // them either hides the progress made or hides the live work.
  const reachedIndex = (() => {
    const started = steps.findIndex(s => s.status.state !== TASK_STATE.PENDING)
    if (started === -1) return 0
    const lastStarted = steps.reduce(
      (acc, s, i) => (s.status.state !== TASK_STATE.PENDING ? i : acc), 0,
    )
    return Math.max(started === 0 ? 0 : lastStarted, lastStarted)
  })()
  const firstUnfinished = steps.findIndex(s => s.status.state !== TASK_STATE.DONE)
  const currentIndex = firstUnfinished === -1 ? Math.max(0, steps.length - 1) : firstUnfinished
  const doneCount = steps.filter(s => s.status.state === TASK_STATE.DONE).length

  // Fraction of *steps cleared*, and how far along the bar the pipeline got.
  // Deliberately separate: a pipeline stalled on step 2 of 5 is 0% cleared but
  // 25% along the bar, and showing "0%" for that would read as "nothing has
  // happened".
  const clearedPct = steps.length ? (doneCount / steps.length) * 100 : 0
  const stepPct = steps.length > 1
    ? (reachedIndex / (steps.length - 1)) * 100
    : (steps.length === 1 && doneCount === 1 ? 100 : 0)

  return {
    flow: { id: flow.id, name: flow.name, createdAt: flow.createdAt },
    progress: {
      total: steps.length,
      doneCount,
      currentIndex,
      currentTaskId: steps[currentIndex]?.id ?? null,
      currentTaskName: steps[currentIndex]?.name ?? null,
      reachedIndex,
      reachedTaskName: steps[reachedIndex]?.name ?? null,
      // True when work is happening on a step earlier than the furthest one
      // reached, i.e. the active and furthest steps disagree.
      outOfOrder: currentIndex < reachedIndex,
      clearedPct: Number(clearedPct.toFixed(1)),
      stepPct: Number(stepPct.toFixed(1)),
      complete: steps.length > 0 && doneCount === steps.length,
      steps: steps.map(s => ({ id: s.id, name: s.name, taskType: s.taskType, state: s.status.state, progressPct: s.status.progressPct })),
    },
    tasks: steps,
  }
}
