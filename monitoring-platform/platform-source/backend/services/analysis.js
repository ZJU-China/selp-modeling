import { exec } from "child_process"
import { promisify } from "util"
import { readFile, mkdir } from "fs/promises"
import { existsSync } from "fs"
import { join } from "path"
import { taskStore } from "../store.js"
import { cacheSet } from "../cache.js"
import { getTaskBaseDir, getTaskCacheDir, getTaskScriptsDir } from "./task-dir.js"

const execAsync = promisify(exec)

const HOME = process.env.HOME || "/home/selp"

function getAnalysisDir(taskId) {
  return join(getTaskCacheDir(taskId), "analysis")
}

// The per-task analyzer needs MDAnalysis (structure/network) + gmx (energies);
// prefer the shared conda env python, with the plain `python3` as fallback.
function resolveAnalyzerPython() {
  const conda = join(HOME, ".local", "miniconda3", "envs", "igem2026", "bin", "python3")
  return [conda, "python3"].find(p => existsSync(p))
}

export async function runLocalAnalysis(taskId) {
  const task = taskStore.tasks.find(t => t.id === taskId)
  const scriptPath = join(getTaskScriptsDir(taskId, task?.taskType), "analyze.py")
  if (!existsSync(scriptPath)) {
    console.error(`[Analysis] Script not found: ${scriptPath}`)
    return false
  }
  console.log(`[Analysis] Running analysis for task ${taskId}...`)
  try {
    const dir = getAnalysisDir(taskId)
    await mkdir(dir, { recursive: true })
    // `;` (not `&&`) separators so e.g. a failed `conda activate` still lets
    // the analyzer run with whatever python3 resolves to; the stdout JSON
    // status line from analyze.py is not required for the cache files we read.
    const python = resolveAnalyzerPython()
    await execAsync(
      `source ~/.bashrc 2>/dev/null; conda activate igem2026 2>/dev/null; ${python} ${scriptPath} ${taskId} --local-dir ${getTaskBaseDir(taskId)}`,
      { timeout: 600000, env: { ...process.env, HOME: process.env.HOME }, shell: "/bin/bash", maxBuffer: 64 * 1024 * 1024 }
    )
    console.log(`[Analysis] Analysis complete for task ${taskId}`)
    return true
  } catch (e) {
    console.error(`[Analysis] Error for task ${taskId}: ${e.message}`)
    return false
  }
}

export async function readAnalysisFile(taskId, filename) {
  const filePath = join(getAnalysisDir(taskId), filename)
  try {
    if (existsSync(filePath)) {
      return await readFile(filePath, "utf8")
    }
  } catch {}
  return null
}

const EMPTY_STRUCTURE = { source: "local", rg: null, e2e: null, rmsd: null, ss: null, energy: null, box: null, crosslink: null, crosslinkTable: null, chainRg: null, meta: null }

export async function loadAnalysisToCache(taskId) {
  const analysisDir = getAnalysisDir(taskId)
  if (!existsSync(analysisDir)) {
    cacheSet(`structure:${taskId}`, { ...EMPTY_STRUCTURE })
    cacheSet(`cluster:${taskId}`, { source: "local", clusters: null, scatter: null })
    return
  }

  const [rg, e2e, rmsd, ss, energy, box, crosslink, crosslinkTable, chainRg, metaRaw] = await Promise.all([
    readAnalysisFile(taskId, "rg.dat"),
    readAnalysisFile(taskId, "e2e.dat"),
    readAnalysisFile(taskId, "rmsd.dat"),
    readAnalysisFile(taskId, "ss.dat"),
    readAnalysisFile(taskId, "energy.dat"),
    readAnalysisFile(taskId, "box.dat"),
    readAnalysisFile(taskId, "crosslink.dat"),
    readAnalysisFile(taskId, "crosslink_table.tsv"),
    readAnalysisFile(taskId, "chain_rg.dat"),
    readAnalysisFile(taskId, "meta.json"),
  ])

  let meta = null
  if (metaRaw) {
    try {
      const i1 = metaRaw.indexOf("{"), i2 = metaRaw.lastIndexOf("}")
      if (i1 !== -1 && i2 !== -1) meta = JSON.parse(metaRaw.slice(i1, i2 + 1))
    } catch {}
  }

  cacheSet(`structure:${taskId}`, {
    source: "local", rg, e2e, rmsd, ss, energy, box, crosslink, crosslinkTable, chainRg, meta,
  })

  try {
    const clusterRaw = await readAnalysisFile(taskId, "cluster_results.json")
    const scatterRaw = await readAnalysisFile(taskId, "cluster_scatter.json")
    const result = { source: "local", clusters: null, scatter: null }
    if (clusterRaw) {
      const i1 = clusterRaw.indexOf("{"), i2 = clusterRaw.lastIndexOf("}")
      if (i1 !== -1 && i2 !== -1) result.clusters = JSON.parse(clusterRaw.slice(i1, i2 + 1))
    }
    if (scatterRaw) {
      const i1 = scatterRaw.indexOf("{"), i2 = scatterRaw.lastIndexOf("}")
      if (i1 !== -1 && i2 !== -1) result.scatter = JSON.parse(scatterRaw.slice(i1, i2 + 1))
    }
    cacheSet(`cluster:${taskId}`, result)
  } catch {}
}

export async function runAndCacheAnalysis(taskId) {
  const ok = await runLocalAnalysis(taskId)
  if (ok) await loadAnalysisToCache(taskId)
  else cacheSet(`structure:${taskId}`, { ...EMPTY_STRUCTURE })
  return ok
}
