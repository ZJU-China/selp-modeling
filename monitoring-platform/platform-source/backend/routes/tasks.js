import { Router } from "express"
import { rm, writeFile, readFile } from "fs/promises"
import { existsSync } from "fs"
import { join } from "path"
import { taskStore, serverStore, flowStore, saveTasks, getDefaultFlowId, isTransitionTask, isLocalTask } from "../store.js"
import { runMain } from "../services/run-main.js"
import { runLocalAnalysis } from "../services/analysis.js"
import { markUserIntent } from "../services/task-guard.js"
import { getServerSession } from "../ssh.js"
import { cacheGet, cacheSet, CACHE_TTL, swrJson, invalidateCache, expireCache } from "../cache.js"
import { getTaskBaseDir, getTaskScriptsDir, scaffoldTaskConfig, ensureTaskDirs, persistTaskConfig, resolveTaskPath } from "../services/task-dir.js"
import { RUN_COMMAND_TIMEOUT_MS, runCommandRejection } from "../services/task-run-commands.js"
import {
  isEditableType, validateEditable, ParamError, annotationsCsv,
  fileFieldFor, checkFieldCsvHeader, typeUsesAnnotations,
} from "../services/editable-params.js"
import { syncFlowLinks } from "../services/flow-links.js"

const router = Router()

router.get("/", async (_req, res) => {
  return swrJson(res, "tasks", CACHE_TTL.tasks, async () => {
    const enrichedTasks = taskStore.tasks.map(t => ({
      ...t, password: undefined,
      serverName: serverStore.servers.find(s => s.id === t.serverId)?.name || "",
      flowName: flowStore.flows.find(f => f.id === t.flowId)?.name || "",
      connected: !!getServerSession(t.serverId),
    }))
    let allProcesses = [], allJobs = []
    // Process/replica scan is owned by the tasktype's main.py (route jobs),
    // so the backend never touches the remote host directly. Scans run in
    // parallel (one SSH round-trip per task) instead of serially — a serial
    // cold recompute after a mutation could hold the response open for
    // tens of seconds.
    const targets = taskStore.tasks.filter(t => t.serverId && getServerSession(t.serverId) && (t.config?.logPrefix || t.name))
    const results = await Promise.all(targets.map(async task => {
      const lp = task.config?.logPrefix || task.name
      try {
        const scan = await runMain(task.id, "route", ["--route", "jobs"], { timeout: 60000 })
        return { task, lp, scan }
      } catch { return null }
    }))
    for (const r of results) {
      if (!r || !r.scan) continue
      allProcesses.push(...(r.scan.processes || []))
      const taskProcesses = (r.scan.processes || []).filter(p => p.command.includes(r.lp))
      const jobGroup = { config: `${r.lp}.conf`, processes: taskProcesses, replicas: r.scan.replicas || {}, running: taskProcesses.length > 0, taskId: r.task.id, taskName: r.task.name }
      // The per-task checkpoint check knows about cluster/slurm runs (log
      // freshness), so prefer its authoritative running flag when cached.
      const cp = cacheGet(`checkpoint:${r.task.id}`, CACHE_TTL.checkpoint)
      if (cp && typeof cp.running === "boolean") jobGroup.running = cp.running
      allJobs.push(jobGroup)
    }
    const runningMap = Object.fromEntries(allJobs.map(j => [j.taskId, j.running]))
    const finalTasks = enrichedTasks.map(t => ({ ...t, running: !!runningMap[t.id] }))
    return { processes: allProcesses, jobs: allJobs, taskConfigs: finalTasks }
  })
})

router.post("/create", async (req, res) => {
  const { name, serverId, workDir = "", scriptName, taskType, logPrefix, flowId, next } = req.body
  if (!name) return res.status(400).json({ error: "name is required" })
  const type = taskType || "tiger2"
  const transition = isTransitionTask({ taskType: type })
  const local = isLocalTask({ taskType: type })
  if (!transition && !local && !serverId) return res.status(400).json({ error: "serverId is required" })
  if (serverId && !serverStore.servers.find(s => s.id === serverId)) return res.status(400).json({ error: "Server not found" })
  // Flow membership: honor an explicit flowId; otherwise fall back to the
  // first flow so every task always belongs to exactly one flow.
  const assignedFlow = flowId && flowStore.flows.some(f => f.id === flowId) ? flowId : getDefaultFlowId()
  if (!assignedFlow) return res.status(400).json({ error: "No flow available; create a flow first" })
  const id = `task_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
  const task = { id, name, serverId: serverId || "", workDir, scriptName: scriptName || "", taskType: type, flowId: assignedFlow, createdAt: Date.now() }
  // `next` tags this task's outputs to a downstream task's input files, e.g.
  // [{ toTaskId: "task_xxx", files: [{ output: "extended.pdb", into: "input/extended.pdb" }] }].
  if (Array.isArray(next)) task.next = next
  taskStore.tasks.push(task)
  await saveTasks()
  // Scaffold <id>/scripts/task_config.json from the tasktype's default
  // template (workDir/logPrefix seed remoteDir/logPrefix; everything else is
  // a FILL-IN placeholder). Never overwrites — see scaffoldTaskConfig.
  const scaffold = await scaffoldTaskConfig(id, type, {
    remoteDir: workDir || undefined,
    logPrefix: logPrefix || undefined,
  })
  await syncFlowLinks()
  expireCache("tasks")
  res.json({ ok: true, task: { ...task, password: undefined }, scaffold })
})

router.put("/update", async (req, res) => {
  const { id, name, serverId, workDir, config, scriptName, taskType, flowId, upstreamTaskId, next } = req.body
  if (!id) return res.status(400).json({ error: "id required" })
  const task = taskStore.tasks.find(t => t.id === id)
  if (!task) return res.status(404).json({ error: "Task not found" })
  if (name !== undefined) task.name = name
  if (serverId !== undefined) task.serverId = serverId
  if (workDir !== undefined) task.workDir = workDir
  if (config !== undefined) task.config = { ...task.config, ...config }
  if (scriptName !== undefined) task.scriptName = scriptName
  if (taskType !== undefined) task.taskType = taskType
  if (flowId !== undefined) {
    if (!flowStore.flows.some(f => f.id === flowId)) return res.status(400).json({ error: "Flow not found" })
    task.flowId = flowId
  }
  if (next !== undefined) {
    task.next = Array.isArray(next) ? next : undefined
  }
  // Pinning the data upstream independently of the displayed step order. Set to
  // "" to go back to positional chaining. The target may live in another flow
  // (e.g. a transition step hidden from the UI), so it is not required to be a
  // member of this flow.
  if (upstreamTaskId !== undefined) {
    const pinned = String(upstreamTaskId || "")
    if (pinned && !taskStore.tasks.some(t => t.id === pinned)) {
      return res.status(400).json({ error: "Upstream task not found" })
    }
    task.upstreamTaskId = pinned || undefined
  }
  await saveTasks()
  await syncFlowLinks()
  // Any field change (name, server, config, flowId/flow membership) alters
  // what GET /api/tasks returns; expire (not delete) the cache so the next
  // refresh serves the last payload instantly and revalidates in the
  // background instead of blocking on a synchronous SSH rescan.
  expireCache("tasks")
  res.json({ ok: true, task: { ...task, password: undefined } })
})

// PUT /api/tasks/:id/params -- save the editable inputs from the Flow Console
// Parameters panel.
//
// Separate from PUT /api/tasks/update because it also validates the values and
// writes them where the task actually reads them: scripts/task_config.json (what
// `main.py --task-config` is handed) and input/annotations.csv (what both the
// generator and /api/data/sequence-annotations read). Without that write-back
// the store would show the new values while the task re-ran the old ones.
//
// Which fields a task type exposes, and what it accepts for them, comes from
// services/editable-params.js -- the same spec the panel was rendered from, so
// the form cannot offer something this endpoint rejects.
router.put("/:id/params", async (req, res) => {
  const task = taskStore.tasks.find(t => t.id === req.params.id)
  if (!task) return res.status(404).json({ error: "Task not found" })
  if (!isEditableType(task.taskType)) {
    return res.status(400).json({ error: `Task type "${task.taskType}" has no editable parameters` })
  }

  const body = req.body || {}
  // The accepted payload shape (including the older flat one) lives in
  // editable-params.js, next to the validation, so the two cannot disagree.
  let validated
  try {
    validated = validateEditable(task.taskType, body, task)
  } catch (e) {
    const status = e instanceof ParamError ? 400 : 500
    return res.status(status).json({ error: e.message, stage: e?.stage || null })
  }
  const { values, annotations: clean } = validated

  // A field-profile CSV is stored as a real file, so it is checked here rather
  // than as a value. The consumer (code/magnetomech/field.py) skips rows whose
  // header it cannot read and returns an empty profile, so a header that looks
  // wrong would otherwise turn into a run reporting a zero field.
  let fieldNote = null
  if (fileFieldFor(task.taskType) && (values.field?.mode === "csv")) {
    const rel = String(values.field.csvPath || "").trim()
    if (!rel) {
      return res.status(400).json({ error: "Field mode is \"From file\" but no profile is uploaded.", stage: "fieldFile" })
    }
    let content
    try {
      content = await readFile(resolveTaskPath(task.id, rel).target, "utf8")
    } catch {
      return res.status(400).json({ error: `Field file "${rel}" was not found in this task's input/.`, stage: "fieldFile" })
    }
    // The sample height matters: it decides whether the file's positions
    // actually span the sample or would clamp to a flat profile.
    const check = checkFieldCsvHeader(content, {
      heightMm: Number(values.field?.heightMm ?? 0),
    })
    if (!check.ok) {
      return res.status(400).json({ error: check.error, stage: "fieldFile" })
    }
    fieldNote = check.note
  }

  task.config = { ...task.config, ...values, annotations: clean }
  await saveTasks()
  await persistTaskConfig(task.id, { ...values, annotations: clean })

  // Sequence-annotation consumers read this file, so it is written from the same
  // rows the generator uses rather than left to drift. Only for types whose
  // panel actually carries a motif table -- writing an empty one elsewhere would
  // leave a file that looks like a deliberate empty annotation set.
  if (typeUsesAnnotations(task.taskType)) {
    await ensureTaskDirs(task.id, "input")
    await writeFile(
      join(getTaskBaseDir(task.id), "input", "annotations.csv"),
      annotationsCsv(clean),
      "utf8",
    )
  }

  expireCache("tasks")
  res.json({ ok: true, config: task.config, task: { ...task, password: undefined } })
})

// POST /api/tasks/:id/run-local – run a local ("no-server") task's compute to
// completion in this process. Local tasks (e.g. magnetomech) never launch a
// remote process, so their "run" is a single blocking main.py invocation — this
// is the standalone equivalent of the isLocal branch in flows.js start, for
// running one step without starting the whole flow. The magnetomech modulus is
// taken from the upstream gromacs_cg task, so that analysis is refreshed first.
router.post("/:id/run-local", async (req, res) => {
  const task = taskStore.tasks.find(t => t.id === req.params.id)
  if (!task) return res.status(404).json({ error: "Task not found" })
  if (!isLocalTask(task)) return res.status(400).json({ error: "Not a local task (use start/ssh-exec)" })

  // Both magnetomech types compute in one shot via the "magnetomech" command;
  // flow_magnetomech runs that same command after regenerating its inputs.
  const computeCommand = task.taskType === "magnetomech" || task.taskType === "flow_magnetomech"
    ? "magnetomech"
    : "start"

  // Refresh the upstream CG rubber-elasticity summary if the previous task in
  // the flow is a gromacs_cg (best-effort — analysis may lag or lack data).
  if (task.flowId) {
    const prev = taskStore.tasks
      .filter(t => t.flowId === task.flowId)
      .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
      .find(t => t.createdAt < (task.createdAt || 0) && t.taskType === "gromacs_cg")
    if (prev) { try { await runLocalAnalysis(prev.id) } catch {} }
  }

  try {
    const r = await runMain(task.id, computeCommand, [], { timeout: 180_000 })
    res.json(r)
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message.slice(0, 2000) })
  }
})

// Task types whose main.py accepts the pause/continue commands added in
// 17007a0. A type not listed here would get "unknown command pause" back from
// main.py, which is a confusing error for the user; say so up front instead.
const PAUSABLE_TYPES = new Set([
  "tiger2", "flow_tiger2", "tiger2_dcd_to_gromacs_cg_pdb",
  "gromacs_cg", "flow_gromacs_cg",
])

// POST /api/tasks/:id/pause and /continue -- suspend or resume the actual
// simulation process. Distinct from the guard's paused flag (POST
// /api/guard/pause), which only stops automatic restarts: the guard flag lets
// a run keep consuming CPU while the UI calls it paused, which is not what the
// user means by pause.
async function handleSignal(req, res, command) {
  const task = taskStore.tasks.find(t => t.id === req.params.id)
  if (!task) return res.status(404).json({ error: "Task not found" })
  if (isLocalTask(task)) {
    return res.status(400).json({
      ok: false,
      error: `${task.taskType} runs to completion in this process, so there is no `
           + "long-running process to suspend. Its Compute button runs it fresh.",
    })
  }
  if (!PAUSABLE_TYPES.has(task.taskType)) {
    return res.status(400).json({
      ok: false,
      error: `${task.taskType} does not support pause/continue`,
    })
  }
  try {
    const r = await runMain(task.id, command, [], { timeout: 60_000 })
    res.json({ ...r, command })
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message.slice(0, 2000) })
  }
}

router.post("/:id/pause", (req, res) => handleSignal(req, res, "pause"))
router.post("/:id/continue", (req, res) => handleSignal(req, res, "continue"))

// POST /api/tasks/:id/start|stop|restart -- drive one step's own main.py.
//
// These are the endpoints the flow console's Run buttons call
// (services/flow-overview.js buildControls); before this they pointed at
// routes that did not exist, so every Start/Stop/Restart was a 404. Unlike
// pause/continue (which only apply to a run in progress), start is how a step
// is kicked off at all when it is not part of a flow start.
async function handleRunCommand(req, res, command) {
  const task = taskStore.tasks.find(t => t.id === req.params.id)
  if (!task) return res.status(404).json({ error: "Task not found" })

  // A step is runnable exactly when it has a main.py to run, the same
  // condition routes/flows.js uses to skip a step. Local one-shot computations
  // and local generation steps are refused before main.py is invoked.
  const scriptsDir = getTaskScriptsDir(task.id, task.taskType)
  const rejection = runCommandRejection(task, command, {
    hasMainPy: existsSync(join(scriptsDir, "main.py")),
    isLocal: isLocalTask(task),
  })
  if (rejection) return res.status(400).json({ ok: false, error: rejection })

  // A user-driven start/stop/restart must not look like a process that died on
  // its own, or the guard races the user with an auto-restart. Same intent
  // marker the ssh-exec script-action route already sets.
  markUserIntent(task.id)
  try {
    const r = await runMain(task.id, command, [], { timeout: RUN_COMMAND_TIMEOUT_MS[command] })
    res.json({ ...r, command })
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message.slice(0, 2000) })
  }
}

router.post("/:id/start", (req, res) => handleRunCommand(req, res, "start"))
router.post("/:id/stop", (req, res) => handleRunCommand(req, res, "stop"))
router.post("/:id/restart", (req, res) => handleRunCommand(req, res, "restart"))

router.delete("/delete", async (req, res) => {
  const { id } = req.body
  const idx = taskStore.tasks.findIndex(t => t.id === id)
  if (idx === -1) return res.status(404).json({ error: "Task not found" })
  taskStore.tasks.splice(idx, 1)
  await saveTasks()
  invalidateCache(id)
  // The GET /api/tasks aggregate would otherwise keep serving the deleted
  // task from its stale cache entry.
  expireCache("tasks")
  await syncFlowLinks()
  try {
    await rm(getTaskBaseDir(id), { recursive: true, force: true })
  } catch (e) {
    console.warn(`[Tasks] Failed to remove task dir for ${id}: ${e.message}`)
  }
  res.json({ ok: true })
})

router.post("/ssh-exec", async (req, res) => {
  const { taskId, command, timeout: cmdTimeout = 30 } = req.body
  if (!taskId || !command) return res.status(400).json({ error: "taskId and command required" })
  try {
    // Arbitrary commands are executed by the task's own main.py (route shell),
    // not directly by the backend.
    // Start/stop/restart actions (sent by the UI's script-action buttons) are
    // the guard's signal that the resulting running->stopped transition was
    // user-initiated, so it won't auto-intervene.
    const action = command.match(/\s(stop|start|restart|continue|pause)\s/)
    if (action) markUserIntent(taskId)
    const r = await runMain(taskId, "route", ["--route", "shell", "--cmd", command, "--timeout", String(cmdTimeout)], { timeout: Math.min(Number(cmdTimeout) * 1000 + 10000, 120000) })
    res.json(r)
  } catch (e) {
    res.status(500).json({ ok: false, exitCode: 1, stdout: "", stderr: e.message.slice(0, 5000), command })
  }
})

export default router
