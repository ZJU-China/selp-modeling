import { writeFile, mkdir, readFile } from "fs/promises"
import { dirname, join } from "path"
import { execFile } from "child_process"
import { taskStore } from "../store.js"
import { getTaskBaseDir, getTaskCacheDir, getTaskScriptsDir, getTaskConfigSync } from "./task-dir.js"
import { runMain, fallbackLogPrefix } from "./run-main.js"

async function ensureDir(dir) {
  await mkdir(dir, { recursive: true })
}

export async function syncSimStatusFiles(taskId) {
  const task = taskStore.tasks.find(t => t.id === taskId)
  if (!task) throw new Error("Task not found")

  const serverId = task.serverId

  console.log(`[SimStatusSync] Syncing sim-status for "${task.name}"...`)

  // Log/config fetch is owned by the task's own main.py (route status), so the
  // backend never talks to the remote host directly.
  if (serverId) {
    try {
      await runMain(taskId, "route", ["--route", "status"], { timeout: 120000 })
    } catch (e) {
      console.warn(`[SimStatusSync] status sync failed: ${e.message}`)
    }
  }

  console.log(`[SimStatusSync] Task "${task.name}" synced successfully`)
}

export async function generateSimStatus(taskId) {
  const task = taskStore.tasks.find(t => t.id === taskId)
  if (!task) throw new Error("Task not found")

  const taskDir = getTaskBaseDir(taskId)
  await ensureDir(taskDir)

  await syncSimStatusFiles(taskId)

  // Log prefix / replica-cycled counts are per-task; prefer task_config.json,
  // fall back to tasks.json config, then the historical default.
  const tcfg = getTaskConfigSync(taskId)
  const lp = tcfg?.logPrefix || task.config?.logPrefix || fallbackLogPrefix(task.taskType)
  const scriptPath = join(getTaskScriptsDir(taskId, task.taskType), "gen_sim_status.py")
  const outputPath = join(getTaskCacheDir(taskId), "sim_status.json")
  await ensureDir(dirname(outputPath))

  await new Promise((resolve, reject) => {
    execFile("python3", [scriptPath, taskDir, outputPath, lp], {
      timeout: 60000,
      maxBuffer: 10 * 1024 * 1024,
    }, (err) => {
      if (err) return reject(new Error(err.message))
      resolve()
    })
  })

  const data = JSON.parse(await readFile(outputPath, "utf8"))

  // Process detection is the task's own main.py's job (status command runs
  // the cluster-aware pgrep/freshness check on the remote). Fall back to the
  // task's checkpoint check (also SSH-aware) only if status cannot be reached.
  if (task.serverId) {
    try {
      const st = await runMain(taskId, "status")
      if (st && typeof st.running === "boolean") data.overall.running = st.running
    } catch (e) {
      try {
        const cp = await runMain(taskId, "checkpoint")
        if (cp && typeof cp.running === "boolean") data.overall.running = cp.running
      } catch {}
    }
  }

  return data
}
