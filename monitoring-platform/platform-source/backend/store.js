import { readFile, writeFile } from "fs/promises"
import { existsSync } from "fs"
import { join, dirname } from "path"
import { fileURLToPath } from "url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const SERVERS_FILE = process.env.MD_SERVERS_FILE || join(__dirname, "servers.json")
const TASKS_FILE = process.env.MD_TASKS_FILE || join(__dirname, "tasks.json")
const FLOWS_FILE = process.env.MD_FLOWS_FILE || join(__dirname, "flows.json")

export const serverStore = { servers: [] }
export const taskStore = { tasks: [] }
export const flowStore = { flows: [] }

// Transitional ("hidden") task types: they run no remote simulation and are
// only ever shown inside Task Control, never in the header task selector.
// The backend treats them as local file generators (see services/transition.js).
export const TRANSITION_TASK_TYPES = new Set(["seq_to_pdb", "tiger2_dcd_to_gromacs_cg_pdb"])

// Local ("no-server") task types: they run a compute entirely on the backend
// host (never SSH), so they are exempt from the serverId requirement. The
// magnetomech tasktype consumes the flow upstream's rubber-elasticity summary
// and produces its field-deformation result + a rendered PNG locally.
export const LOCAL_TASK_TYPES = new Set(["magnetomech", "flow_magnetomech"])

export function isTransitionTask(task) {
  return !!task && TRANSITION_TASK_TYPES.has(task.taskType)
}

export function isLocalTask(task) {
  return !!task && LOCAL_TASK_TYPES.has(task.taskType)
}

export async function loadServers() {
  try {
    if (existsSync(SERVERS_FILE)) {
      Object.assign(serverStore, JSON.parse(await readFile(SERVERS_FILE, "utf8")))
    }
  } catch {}
}

export async function saveServers() {
  try { await writeFile(SERVERS_FILE, JSON.stringify(serverStore, null, 2)) }
  catch (e) { console.error("[Servers] Save error:", e.message) }
}

export async function loadTasks() {
  try {
    if (existsSync(TASKS_FILE)) {
      Object.assign(taskStore, JSON.parse(await readFile(TASKS_FILE, "utf8")))
    }
  } catch {}
}

export async function saveTasks() {
  try { await writeFile(TASKS_FILE, JSON.stringify(taskStore, null, 2)) }
  catch (e) { console.error("[Tasks] Save error:", e.message) }
}

export async function loadFlows() {
  try {
    if (existsSync(FLOWS_FILE)) {
      Object.assign(flowStore, JSON.parse(await readFile(FLOWS_FILE, "utf8")))
    }
  } catch {}
}

export async function saveFlows() {
  try { await writeFile(FLOWS_FILE, JSON.stringify(flowStore, null, 2)) }
  catch (e) { console.error("[Flows] Save error:", e.message) }
}

export function migrateLegacyData() {
  for (const task of taskStore.tasks) {
    if (task.serverId) continue
    if (!task.host || !task.username) continue
    let server = serverStore.servers.find(s => s.host === task.host && s.username === task.username)
    if (!server) {
      const id = `srv_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
      server = {
        id,
        name: serverStore.servers.length === 0 ? "iGEM Server" : `Server ${serverStore.servers.length + 1}`,
        host: task.host,
        port: task.port || 22,
        username: task.username,
        password: task.password || "",
      }
      serverStore.servers.push(server)
      console.log(`[Migration] Created server "${server.name}" from task "${task.name}"`)
    }
    task.serverId = server.id
  }
}

// Ensure every task belongs to a flow (flows are the grouping unit of Task
// Control). Tasks without a flowId — including everything created before the
// flow feature — land in the first available flow, so the "all tasks in a
// flow" invariant always holds.
export function ensureFlows() {
  if (flowStore.flows.length === 0) {
    flowStore.flows.push({
      id: `flow_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      name: "Unfiled",
      createdAt: Date.now(),
    })
  }
  const first = flowStore.flows[0].id
  for (const task of taskStore.tasks) {
    if (!task.flowId || !flowStore.flows.some(f => f.id === task.flowId)) {
      task.flowId = first
    }
    if (!task.createdAt) task.createdAt = Date.now()
  }
}

export function getDefaultFlowId() {
  return flowStore.flows.length ? flowStore.flows[0].id : null
}

export async function initStore() {
  await loadServers()
  await loadTasks()
  await loadFlows()
  migrateLegacyData()
  ensureFlows()
  await saveServers()
  await saveTasks()
  await saveFlows()
}
