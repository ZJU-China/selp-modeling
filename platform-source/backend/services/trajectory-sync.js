import { readFile, writeFile, mkdir } from "fs/promises"
import { existsSync } from "fs"
import { join } from "path"
import { taskStore } from "../store.js"
import { getTaskCacheDir, getTaskInputDir, getTaskOutputDir } from "./task-dir.js"
import { runMain } from "./run-main.js"

const syncIntervals = new Map()

export async function getTrajectoryCacheDir(taskId) {
  const dir = join(await getTaskCacheDir(taskId), "trajectory")
  await mkdir(dir, { recursive: true })
  return dir
}

export async function getTrajectoryStatus(taskId) {
  const cacheDir = await getTrajectoryCacheDir(taskId)
  const statusFile = join(cacheDir, "status.json")
  try {
    if (existsSync(statusFile)) {
      return JSON.parse(await readFile(statusFile, "utf8"))
    }
  } catch {}
  return { generatedAt: 0, pdbFrames: 0, dcdFrames: 0, pdbSize: 0, dcdSize: 0, last100Sizes: [], last100Frames: [], taskId }
}

async function updateTrajectoryStatus(taskId, status) {
  const cacheDir = await getTrajectoryCacheDir(taskId)
  const statusFile = join(cacheDir, "status.json")
  await writeFile(statusFile, JSON.stringify(status, null, 2))
}

// In-flight dedupe per task: concurrent syncs for the same task (e.g. an MP4
// and a GIF render starting together on a cold cache) would download and merge
// DCD segments into the same cache/trajectory files at once. The first caller
// wins, everyone else shares its promise.
const syncInFlight = new Map()

export function syncTrajectoryFiles(taskId) {
  if (syncInFlight.has(taskId)) return syncInFlight.get(taskId)
  const p = doSyncTrajectoryFiles(taskId)
  syncInFlight.set(taskId, p)
  const cleanup = () => { if (syncInFlight.get(taskId) === p) syncInFlight.delete(taskId) }
  p.then(cleanup, cleanup)
  return p
}

// Remote file discovery (topology names, .dcd globs, production dir via log
// symlink) AND the actual downloads are owned by the task's own main.py
// (route trajectory), so the backend never talks to the remote host directly.
async function doSyncTrajectoryFiles(taskId) {
  const task = taskStore.tasks.find(t => t.id === taskId)
  if (!task) throw new Error("Task not found")

  const cacheDir = await getTrajectoryCacheDir(taskId)

  console.log(`[TrajectorySync] Syncing trajectory for task "${task.name}"...`)

  try {
    if (!task.serverId) return false
    const res = await runMain(taskId, "route", ["--route", "trajectory"], { timeout: 900000 })
    if (!res || res.ok === false) {
      console.error(`[TrajectorySync] ${res?.error || "sync failed"}`)
      return false
    }

    await updateTrajectoryStatus(taskId, {
      generatedAt: Date.now(),
      pdbSize: res.pdbSize ?? 0,
      dcdSize: res.dcdSize ?? 0,
      dcdSizes: res.dcdSizes || [],
      previewSizes: res.previewSizes || [],
      previewFrames: res.previewFrames || [],
      samples: res.samples || [],
      replicaSizes: res.replicaSizes || [],
      last100Sizes: res.last100Sizes || [],
      last100Frames: res.last100Frames || [],
      taskId
    })

    console.log(`[TrajectorySync] Task "${task.name}" synced successfully`)
    return true
  } catch (e) {
    console.error(`[TrajectorySync] Failed to sync task "${task.name}": ${e.message}`)
    return false
  }
}

export function startTrajectorySync(taskId, intervalMs = 60000) {
  if (syncIntervals.has(taskId)) return

  console.log(`[TrajectorySync] Starting sync for task ${taskId} (interval: ${intervalMs}ms)`)
  
  // Initial sync
  syncTrajectoryFiles(taskId).catch(() => {})

  // Set up periodic sync
  const interval = setInterval(() => {
    syncTrajectoryFiles(taskId).catch(() => {})
  }, intervalMs)
  
  syncIntervals.set(taskId, interval)
}

export function stopTrajectorySync(taskId) {
  const interval = syncIntervals.get(taskId)
  if (interval) {
    clearInterval(interval)
    syncIntervals.delete(taskId)
    console.log(`[TrajectorySync] Stopped sync for task ${taskId}`)
  }
}

export function stopAllTrajectorySync() {
  for (const [taskId, interval] of syncIntervals) {
    clearInterval(interval)
    console.log(`[TrajectorySync] Stopped sync for task ${taskId}`)
  }
  syncIntervals.clear()
}

export async function getPDBData(taskId) {
  const cacheDir = await getTrajectoryCacheDir(taskId)
  const pdbPath = join(cacheDir, "topology.pdb")
  const inputPdb = join(getTaskInputDir(taskId), "topology.pdb")
  
  if (existsSync(pdbPath)) {
    return await readFile(pdbPath, "utf8")
  }
  if (existsSync(inputPdb)) {
    return await readFile(inputPdb, "utf8")
  }
  return null
}

export async function getDCDData(taskId, replica = 0) {
  const cacheDir = await getTrajectoryCacheDir(taskId)
  const replicaPath = join(cacheDir, `replica_${replica}.dcd`)
  const outputPath = join(getTaskOutputDir(taskId), String(replica), `replica_${replica}.dcd`)
  
  if (existsSync(replicaPath)) {
    return await readFile(replicaPath)
  }
  if (existsSync(outputPath)) {
    return await readFile(outputPath)
  }
  return null
}
