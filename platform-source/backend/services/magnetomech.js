import { readFile, mkdir } from "fs/promises"
import { existsSync } from "fs"
import { join } from "path"
import { getTaskBaseDir, getTaskCacheDir } from "./task-dir.js"
import { cacheSet } from "../cache.js"
import { runMain } from "./run-main.js"

// Magnetomech is a local computation tasktype: `main.py magnetomech` runs
// code/magnetomech/run.py and writes its artifacts into
// <task_dir>/cache/magnetomech/{magnetomech.summary.json,curve.csv,layer.csv}.
// This service mirrors loadAnalysisToCache from analysis.js.

export function getMagnetomechDir(taskId) {
  return join(getTaskCacheDir(taskId), "magnetomech")
}

// final_simulation.png rendered by code/magnetomech/run.py when matplotlib or
// Pillow is available (see backend tasktype magnetomech/main.py python picker).
export function getMagnetomechImagePath(taskId) {
  return join(getMagnetomechDir(taskId), "final_simulation.png")
}

export function hasMagnetomechData(d) {
  return !!(d && d.data && d.data.summary && typeof d.data.summary.youngKpa === "number")
}

export async function loadMagnetomechToCache(taskId) {
  const dir = getMagnetomechDir(taskId)
  const out = { source: "local", data: null }
  const summaryPath = join(dir, "magnetomech.summary.json")
  if (existsSync(summaryPath)) {
    try {
      out.data = JSON.parse(await readFile(summaryPath, "utf8"))
    } catch {}
  }
  if (out.data && out.data.summary && out.data.summary.modulusSource) {
    out.modulusSource = out.data.summary.modulusSource
  }
  out.image = existsSync(getMagnetomechImagePath(taskId)) ? "final_simulation.png" : null
  cacheSet(`magnetomech:${taskId}`, out)
  return out
}

export async function runAndCacheMagnetomech(taskId) {
  const task = undefined // runMain resolves the task internally
  await runMain(taskId, "magnetomech", [], { timeout: 120000 })
  return loadMagnetomechToCache(taskId)
}