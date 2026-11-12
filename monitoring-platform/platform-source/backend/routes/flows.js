import { Router } from "express"
import { join, dirname } from "path"
import { fileURLToPath } from "url"
import { existsSync } from "fs"
import { mkdir, cp, readdir } from "fs/promises"
import { flowStore, taskStore, saveFlows, saveTasks, isLocalTask } from "../store.js"
import { runLocalAnalysis } from "../services/analysis.js"
import { syncFlowLinks } from "../services/flow-links.js"
import { expireCache } from "../cache.js"
import { runMain } from "../services/run-main.js"
import { getTaskBaseDir, getTaskInputDir, getTaskOutputDir, getTaskScriptsDir, scaffoldTaskConfig } from "../services/task-dir.js"
import { syncFlowFolder, removeFlowFolder } from "../services/flow-folder.js"
import { getServerSession } from "../ssh.js"

const router = Router()

router.get("/", (_req, res) => {
  const flows = flowStore.flows.map(f => ({
    ...f,
    taskCount: taskStore.tasks.filter(t => t.flowId === f.id).length,
  }))
  res.json({ flows })
})

router.post("/create", async (req, res) => {
  const { name } = req.body
  if (!name || !String(name).trim()) return res.status(400).json({ error: "Flow name required" })
  const flow = {
    id: `flow_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    name: String(name).trim(),
    createdAt: Date.now(),
  }
  flowStore.flows.push(flow)
  await saveFlows()
  // Materialise backend/flows/<flow name>/ for the flow-centric pages.
  syncFlowFolder(flow).catch(e => console.error("[Flows] folder sync:", e.message))
  res.json({ ok: true, flow })
})

router.put("/rename", async (req, res) => {
  const { id, name } = req.body
  const flow = flowStore.flows.find(f => f.id === id)
  if (!flow) return res.status(404).json({ error: "Flow not found" })
  if (!name || !String(name).trim()) return res.status(400).json({ error: "Flow name required" })
  const oldFolder = flow.name
  flow.name = String(name).trim()
  await saveFlows()
  // The folder is named after the flow, so a rename leaves the old folder
  // behind. Drop it and re-materialise under the new name.
  if (oldFolder !== flow.name) {
    removeFlowFolder({ ...flow, name: oldFolder }).catch(() => {})
    syncFlowFolder(flow).catch(e => console.error("[Flows] folder sync:", e.message))
  }
  // Renaming changes the flowName each task enriches. Expire (not delete)
  // the tasks cache so clients keep getting an instant response while the
  // background revalidation picks up the new name.
  expireCache("tasks")
  res.json({ ok: true })
})

router.delete("/delete", async (req, res) => {
  const { id } = req.body
  const flow = flowStore.flows.find(f => f.id === id)
  if (!flow) return res.status(404).json({ error: "Flow not found" })
  const count = taskStore.tasks.filter(t => t.flowId === id).length
  if (count > 0) {
    return res.status(400).json({ error: `Flow is not empty (${count} task(s)); move them before deleting` })
  }
  flowStore.flows = flowStore.flows.filter(f => f.id !== id)
  await saveFlows()
  removeFlowFolder(flow).catch(() => {})
  expireCache("tasks")
  res.json({ ok: true })
})

// ---------------------------------------------------------------------------
// POST /api/flows/:id/start  –  automatic sequential pipeline launcher
//
// Runs every task in a flow in creation order.  Between tasks it copies the
// predecessor's output into the successor's input (honouring the `next` file
// map).  Transition tasks (tiger2_dcd_to_gromacs_cg_pdb, seq_to_pdb) are awaited until they
// finish; compute tasks (tiger2, gromacs_cg) are started and only monitored
// for a short window to confirm they launched successfully.
// ---------------------------------------------------------------------------
// ensureMagnetomechStep(flowId) – auto-append a magnetomech compute step
//
// When a flow contains a GROMACS CG upstream but no magnetomech task yet, the
// "magnetomech" step (CG modulus chain analysis) is auto-created as a local,
// serverless task placed immediately after the last gromacs_cg task in pipeline
// order. This lets flow start "just work" for the CG -> magnetomech chain:
// magnetomech reads the CG rubber-elasticity summary through the flow-<prev>
// symlink created by syncFlowLinks. Idempotent: once a magnetomech task exists
// in the flow nothing more is created.
export async function ensureMagnetomechStep(flowId) {
  const tasks = taskStore.tasks
    .filter(t => t.flowId === flowId)
    .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))

  const lastCgIdx = tasks.reduce((acc, t, i) => t.taskType === "gromacs_cg" ? i : acc, -1)
  if (lastCgIdx === -1) return { created: false, reason: "no-gromacs-cg" }
  // Count both spellings: a flow that already has the step in either form must
  // not gain a second one when the type is upgraded.
  if (tasks.some(t => t.taskType === "magnetomech" || t.taskType === "flow_magnetomech")) {
    return { created: false, reason: "already-exists" }
  }

  const upstream = tasks[lastCgIdx]
  const flow = flowStore.flows.find(f => f.id === flowId)
  const mm = {
    id: `task_mm_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    name: `${flow ? flow.name : "Flow"} → Magnetomech`,
    serverId: "",
    workDir: "",
    scriptName: "",
    // The editable type: the composite fractions and the field profile are
    // panel inputs that get re-derived on every run.
    taskType: "flow_magnetomech",
    flowId,
    // Sort immediately after the gromacs_cg upstream so the flow-<prev> link
    // (see flow-links.js) points at the CG task's output.
    createdAt: upstream.createdAt + 1,
  }
  taskStore.tasks.push(mm)
  await saveTasks()
  await scaffoldTaskConfig(mm.id, "flow_magnetomech", {})
  await syncFlowLinks()
  expireCache("tasks")
  return { created: true, taskId: mm.id, name: mm.name, upstream: upstream.id }
}
// ---------------------------------------------------------------------------

// POST /api/flows/:id/append-magnetomech – add the magnetomech step to a flow
// without starting it. Same helper the flow start auto-append uses, exposed so
// the step can be materialised up front (idempotent: a flow that already has a
// magnetomech task is left untouched).
router.post("/:id/append-magnetomech", async (req, res) => {
  const flow = flowStore.flows.find(f => f.id === req.params.id)
  if (!flow) return res.status(404).json({ error: "Flow not found" })
  const r = await ensureMagnetomechStep(flow.id)
  res.json({ ok: true, ...r })
})

// ---------------------------------------------------------------------------
// POST /api/flows/:id/start  –  automatic sequential pipeline launcher
//
// Runs every task in a flow in creation order.  Between tasks it copies the
// predecessor's output into the successor's input (honouring the `next` file
// map).  Transition tasks (tiger2_dcd_to_gromacs_cg_pdb, seq_to_pdb) are awaited until they
// finish; compute tasks (tiger2, gromacs_cg) are started and only monitored
// for a short window to confirm they launched successfully.
// ---------------------------------------------------------------------------
router.post("/:id/start", async (req, res) => {
  const { id } = req.params
  const { dryRun, waitForCompletion } = req.body || {}
  const flow = flowStore.flows.find(f => f.id === id)
  if (!flow) return res.status(404).json({ error: "Flow not found" })

  let tasks = taskStore.tasks
    .filter(t => t.flowId === id)
    .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))

  if (tasks.length === 0) return res.status(400).json({ error: "Flow has no tasks" })

  // Auto-append the magnetomech step when the flow has a GROMACS CG upstream
  // but no magnetomech yet. Skipped for dryRun (no mutation).
  const autoCreated = []
  if (!dryRun) {
    const mm = await ensureMagnetomechStep(id)
    if (mm.created) {
      autoCreated.push({ taskId: mm.taskId, name: mm.name, upstream: mm.upstream })
      // Re-sort so the new step executes right after its upstream.
      tasks = taskStore.tasks
        .filter(t => t.flowId === id)
        .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
    }
  }

  const results = []
  // Set when the chain stopped because a compute step is still running.
  let waiting = null
  const TRANSITION_TYPES = new Set(["seq_to_pdb", "tiger2_dcd_to_gromacs_cg_pdb"])

  for (let i = 0; i < tasks.length; i++) {
    const task = tasks[i]
    const prev = i > 0 ? tasks[i - 1] : null
    const step = { taskId: task.id, taskType: task.taskType, name: task.name, actions: [] }

    // ---- 1. Copy predecessor outputs into this task's input ----
    if (prev && prev.next) {
      for (const link of prev.next) {
        if (link.toTaskId !== task.id) continue
        const prevOut = getTaskOutputDir(prev.id)
        const thisIn = getTaskInputDir(task.id)
        await mkdir(thisIn, { recursive: true })
        for (const f of link.files || []) {
          const src = join(prevOut, f.output)
          const into = (f.into || f.output).replace(/^input\//, "")
          const dst = join(thisIn, into)
          if (!existsSync(src)) {
            step.actions.push({ op: "copy-skip", src: f.output, reason: "source missing" })
            continue
          }
          const dstDir = join(dst, "..")
          await mkdir(dstDir, { recursive: true })
          try {
            await cp(src, dst, { recursive: true })
            step.actions.push({ op: "copy", from: `${prev.id}/output/${f.output}`, to: `input/${into}` })
          } catch (e) {
            step.actions.push({ op: "copy-error", from: f.output, error: e.message })
          }
        }
      }
    }

    // ---- 2. Start the task ----
    if (dryRun) {
      step.start = { dryRun: true }
      results.push(step)
      continue
    }

    const isLocal = isLocalTask(task)

    // Skip start for tasks with no main.py (local-only generation tasks like seq_to_pdb)
    const scriptsDir = getTaskScriptsDir(task.id, task.taskType)
    const hasMainPy = existsSync(join(scriptsDir, "main.py"))
    if (!hasMainPy) {
      step.start = { ok: true, skipped: true, reason: "no main.py (local generation task)" }
      step.monitor = { skipped: true }
      results.push(step)
      continue
    }
    // Check server connectivity for tasks that need SSH (local tasks don't)
    const hasServer = task.serverId && getServerSession(task.serverId)
    if (!isLocal && !hasServer && task.serverId) {
      step.start = { ok: false, error: `Server ${task.serverId} not connected` }
      results.push(step)
      if (!TRANSITION_TYPES.has(task.taskType)) break
      continue
    }

    // Local compute tasks (e.g. magnetomech) run to completion right here —
    // they never launch a background remote process, so "start" is their
    // whole run, not just a launch confirmation.
    if (isLocal) {
      // Both magnetomech types compute in one shot via the "magnetomech"
      // command; flow_magnetomech runs that same command after regenerating
      // its composite fractions and field profile from the panel.
      const computeCommand = task.taskType === "magnetomech" || task.taskType === "flow_magnetomech"
        ? "magnetomech"
        : "start"
      // The magnetomech modulus comes from the upstream gromacs_cg task's
      // rubber-elasticity summary; make sure that analysis is fresh first
      // (best-effort — flows start is where analysis usually lags behind).
      if (prev && prev.taskType === "gromacs_cg") {
        try { await runLocalAnalysis(prev.id) } catch {}
      }
      try {
        const r = await runMain(task.id, computeCommand, [], { timeout: 180_000 })
        step.start = r
        step.monitor = { local: true, ok: !!r?.ok, error: r?.error }
      } catch (e) {
        step.start = { ok: false, error: e.message.slice(0, 500) }
        step.monitor = { local: true, ok: false, error: step.start.error }
      }
      results.push(step)
      if (!step.monitor.ok) break
      continue
    }

    try {
      const startResult = await runMain(task.id, "start", [], { timeout: 180_000 })
      step.start = startResult
    } catch (e) {
      step.start = { ok: false, error: e.message.slice(0, 500) }
      results.push(step)
      // If start failed for a non-transition task, stop the pipeline
      if (!TRANSITION_TYPES.has(task.taskType)) break
      // Transition tasks may fail because predecessor data is missing – continue
    }

    // ---- 3. Monitor: transition tasks are awaited; compute tasks are just verified ----
    if (TRANSITION_TYPES.has(task.taskType)) {
      // Poll status for up to 120 s (transition tasks are fast)
      const deadline = Date.now() + 120_000
      let running = true
      while (running && Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 3_000))
        try {
          const st = await runMain(task.id, "status", [], { timeout: 15_000 })
          running = st?.running
        } catch { running = false }
      }
      step.monitor = { waited: true, finalRunning: running }
      // Still producing output after the wait: its files are incomplete, so the
      // successor must not be started on a half-written conversion.
      if (running && !dryRun && !waitForCompletion) {
        waiting = {
          taskId: task.id,
          taskType: task.taskType,
          name: task.name,
          reason: "This step is still running after its wait window, so its output is "
            + "incomplete. Start this flow again later to continue the chain.",
        }
        results.push(step)
        break
      }
    } else {
      // Compute task – check if start reported success
      const startOk = step.start?.ok ?? step.start?.start?.ok ?? false
      const isRunning = step.start?.running ?? step.start?.start?.running ?? step.start?.pid === "started"
      step.monitor = { started: startOk, running: isRunning }
    }

    results.push(step)

    // If a compute task didn't start, stop the pipeline
    if (!TRANSITION_TYPES.has(task.taskType)) {
      const ok = step.monitor?.started ?? false
      if (!ok && step.start && !step.start.skipped) {
        step.error = step.error || "task did not start"
        break
      }
      // A compute step that launched successfully is still running. The next
      // step reads its output, and that output does not exist yet, so carrying
      // on would copy "source missing" for every handoff file and then start a
      // downstream run against an empty input directory -- the chain reported
      // success while producing nothing.
      //
      // So the pipeline stops here and says which step it is waiting on.
      // Re-running start on the flow resumes from the top: finished steps are
      // recognised and skipped, and the chain continues once the waiting step
      // has completed.
      if (ok && isRunning && !dryRun && !waitForCompletion) {
        waiting = {
          taskId: task.id,
          taskType: task.taskType,
          name: task.name,
          reason: "This step is still running. Its output does not exist yet, so the next "
            + "step cannot start. Start this flow again after it finishes to continue the chain.",
        }
        break
      }
    }
  }

  const ok = !waiting && results.every(s => !s.error && (s.start?.ok ?? s.start?.skipped ?? true))
  res.json({
    ok,
    flow: { id: flow.id, name: flow.name },
    steps: results,
    autoCreated,
    ...(waiting ? { waiting } : {}),
    ...(ok ? {} : { error: waiting ? "chain is waiting on a running step" : undefined }),
  })
})

export default router
