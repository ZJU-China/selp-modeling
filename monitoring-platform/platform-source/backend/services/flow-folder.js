import { join, dirname } from "path"
import { fileURLToPath } from "url"
import { mkdir, writeFile, readFile, readdir, stat } from "fs/promises"
import { existsSync } from "fs"
import { taskStore, flowStore } from "../store.js"

const __dirname = dirname(fileURLToPath(import.meta.url))

// Flow-scoped workspace root. `backend/flows/` is a *projection* of
// tasks.json/flows.json: one folder per flow named after that flow, each
// holding a copy of just that flow's tasks plus a small meta file.
//
// The originals (backend/tasks.json, backend/flows.json, backend/tasks/<id>/)
// are the single source of truth and are never modified by anything here. This
// folder exists so a flow can be inspected, copied, or shipped on its own
// without dragging the other flows' tasks (and their SSH credentials) along.
export const FLOWS_DIR = process.env.MD_FLOWS_DIR || join(__dirname, "..", "flows")

// Turn a flow name into a stable, filesystem-safe folder name.
// "TIGER2 GPU -> CG E2E smoke" -> "TIGER2 GPU - CG E2E smoke"
export function flowSlug(name, id) {
  const base = String(name || "")
    .replace(/[\\/:*?"<>|]+/g, "")   // characters illegal on Windows/Linux
    .replace(/\s+/g, " ")
    .replace(/^\.+/, "")
    .replace(/\.+$/, "")
    .trim()
  const safe = base.slice(0, 80)
  return safe || String(id || "flow").replace(/[^A-Za-z0-9._-]/g, "_")
}

// A directory name must be unique even if two flows share a display name, so
// append a short id discriminator when the bare name is already taken by a
// *different* flow id.
export function flowFolderName(flow, allFlows = flowStore.flows) {
  const base = flowSlug(flow.name, flow.id)
  const clash = allFlows.some(
    f => f.id !== flow.id && flowSlug(f.name, f.id) === base,
  )
  return clash ? `${base}__${flow.id}` : base
}

export function getFlowDir(flow, allFlows = flowStore.flows) {
  return join(FLOWS_DIR, flowFolderName(flow, allFlows))
}

// Never copy connection secrets into a per-flow folder. The flow pages render
// parameters and results, never credentials, and backend/tasks.json is the only
// place they are needed (services/ssh.js reads the live store).
const SECRET_FIELDS = new Set(["password", "privateKey", "private_key"])

function redactTask(task) {
  const copy = { ...task }
  for (const k of Object.keys(copy)) {
    if (SECRET_FIELDS.has(k)) copy[k] = ""
  }
  return copy
}

// A task with no server runs locally on the backend host (magnetomech) and
// therefore has no host/username to leak either.
export function sanitizeTaskForFlowFolder(task) {
  const out = redactTask(task)
  delete out.host
  delete out.port
  delete out.username
  delete out.sshSessionId
  return out
}

export function orderedFlowTasks(flowId) {
  return taskStore.tasks
    .filter(t => t.flowId === flowId)
    .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
}

async function writeJson(path, data) {
  await writeFile(path, JSON.stringify(data, null, 2) + "\n")
}

// Write (or refresh) <flows>/<flow name>/ for one flow.
// Returns { dir, tasks: n, created }.
export async function syncFlowFolder(flow, allFlows = flowStore.flows) {
  const dir = getFlowDir(flow, allFlows)
  const created = !existsSync(dir)
  await mkdir(dir, { recursive: true })

  const tasks = orderedFlowTasks(flow.id).map(sanitizeTaskForFlowFolder)

  await writeJson(join(dir, "tasks.json"), {
    flow: { id: flow.id, name: flow.name, createdAt: flow.createdAt },
    taskCount: tasks.length,
    tasks,
  })
  await writeJson(join(dir, "meta.json"), {
    id: flow.id,
    name: flow.name,
    createdAt: flow.createdAt,
    folder: flowFolderName(flow, allFlows),
    taskCount: tasks.length,
    taskIds: tasks.map(t => t.id),
    // Tasks in pipeline order — the order the progress bar walks.
    pipeline: tasks.map((t, i) => ({ index: i, id: t.id, name: t.name, taskType: t.taskType })),
    // Per-task on-disk workspace, so the folder is self-describing.
    workspaces: tasks.map(t => ({ id: t.id, path: `../tasks/${t.id}` })),
    note: "Read-only projection of backend/tasks.json. The original store is authoritative; edit there, not here.",
  })
  return { dir, tasks: tasks.length, created }
}

export async function syncAllFlowFolders() {
  await mkdir(FLOWS_DIR, { recursive: true })
  const out = []
  for (const flow of flowStore.flows) {
    out.push(await syncFlowFolder(flow))
  }
  return out
}

// Remove a flow's folder. Called when a flow is deleted.
export async function removeFlowFolder(flow, allFlows = flowStore.flows) {
  const dir = getFlowDir(flow, allFlows)
  if (!existsSync(dir)) return false
  const { rm } = await import("fs/promises")
  await rm(dir, { recursive: true, force: true })
  return true
}

// List what is currently on disk under backend/flows/ (for diagnostics).
export async function listFlowFolders() {
  if (!existsSync(FLOWS_DIR)) return []
  const entries = await readdir(FLOWS_DIR, { withFileTypes: true })
  const out = []
  for (const e of entries) {
    if (!e.isDirectory()) continue
    const metaPath = join(FLOWS_DIR, e.name, "meta.json")
    let meta = null
    try { meta = JSON.parse(await readFile(metaPath, "utf8")) } catch {}
    out.push({ folder: e.name, meta })
  }
  return out
}
