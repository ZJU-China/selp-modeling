import { Router } from "express"
import { join } from "path"
import { existsSync, readFileSync } from "fs"
import { flowStore, taskStore } from "../store.js"
import {
  buildFlowOverview, buildParamsPanel, normalizeStatus, readArtifacts,
} from "../services/flow-overview.js"
import { buildExecution } from "../services/task-execution.js"
import {
  FLOWS_DIR, flowFolderName, getFlowDir, orderedFlowTasks,
  syncAllFlowFolders, syncFlowFolder, removeFlowFolder, listFlowFolders,
} from "../services/flow-folder.js"

const router = Router()

function findFlow(id) {
  return flowStore.flows.find(f => f.id === id)
}

// The default flow (flows[0]) is the bucket that tasks fall into when no flow is
// assigned — getDefaultFlowId() in store.js points at it. It is a staging area
// for loose tasks, not a pipeline, so it is not listed as a page. Its tasks stay
// fully reachable through the original task-centric app.
function isDraftFlow(flow) {
  if (flowStore.flows[0]?.id === flow.id) return true
  return !String(flow.name || "").trim() || /^(unfiled|untitled)$/i.test(flow.name.trim())
}

// GET /api/flows/pages
// Lightweight index for the flow-centric UI: every flow plus its progress
// summary, so the landing page does not need one overview request per flow.
router.get("/pages", async (_req, res) => {
  const out = []
  for (const flow of flowStore.flows) {
    if (isDraftFlow(flow)) continue
    const tasks = orderedFlowTasks(flow.id)
    const overview = await buildFlowOverview(flow, tasks)
    out.push({
      id: flow.id,
      name: flow.name,
      createdAt: flow.createdAt,
      taskCount: tasks.length,
      progress: overview.progress,
      folder: flowFolderName(flow),
    })
  }
  res.json({ flows: out, flowsDir: FLOWS_DIR })
})

// GET /api/flows/:id/overview
// Everything one flow page needs: ordered steps, normalised status,
// per-task-type parameter panels, available result artefacts, controls, and the
// flow progress the progress bar renders.
router.get("/:id/overview", async (req, res) => {
  const flow = findFlow(req.params.id)
  if (!flow) return res.status(404).json({ error: "Flow not found" })
  const tasks = orderedFlowTasks(flow.id)
  const overview = await buildFlowOverview(flow, tasks)
  res.json({
    ...overview,
    folder: flowFolderName(flow),
    folderPath: getFlowDir(flow),
    sourceOfTruth: "backend/tasks.json (backend/flows/ is a read-only projection)",
  })
})

// GET /api/flows/:id/task/:taskId
// Per-task detail on its own, so expanding one card in the UI does not refetch
// the whole flow. Shape matches the matching entry in the overview payload.
router.get("/:id/task/:taskId", async (req, res) => {
  const flow = findFlow(req.params.id)
  if (!flow) return res.status(404).json({ error: "Flow not found" })
  const task = taskStore.tasks.find(t => t.id === req.params.taskId)
  if (!task) return res.status(404).json({ error: "Task not found" })
  if (task.flowId !== flow.id) {
    return res.status(400).json({ error: "Task does not belong to this flow" })
  }
  const index = orderedFlowTasks(flow.id).findIndex(t => t.id === task.id)
  res.json({
    index,
    id: task.id,
    name: task.name,
    taskType: task.taskType,
    status: normalizeStatus(task),
    params: buildParamsPanel(task),
    // The execution environment (real SSH host, data paths, resolved tool
    // commands) so the panel can state where this task runs instead of the
    // user inferring it.
    execution: await buildExecution(task),
    artifacts: readArtifacts(task.id),
    workDir: task.workDir || null,
  })
})

// GET /api/flows/:id/folder -- the flow-scoped copy on disk
router.get("/:id/folder", async (req, res) => {
  const flow = findFlow(req.params.id)
  if (!flow) return res.status(404).json({ error: "Flow not found" })
  const dir = getFlowDir(flow)
  if (!existsSync(dir)) {
    return res.status(404).json({ error: "Flow folder not synced yet", dir })
  }
  try {
    res.json(JSON.parse(readFileSync(join(dir, "tasks.json"), "utf8")))
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// POST /api/flows/folders/sync -- (re)write every backend/flows/<name>/ folder
// from the live store. Safe to call repeatedly; it only ever writes inside
// backend/flows and never touches backend/tasks.json.
router.post("/folders/sync", async (_req, res) => {
  try {
    const out = await syncAllFlowFolders()
    res.json({ ok: true, flowsDir: FLOWS_DIR, synced: out })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

router.get("/folders", async (_req, res) => {
  try {
    res.json({ flowsDir: FLOWS_DIR, folders: await listFlowFolders() })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

export default router
