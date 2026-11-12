import { Router } from "express"
import { existsSync } from "fs"
import { join } from "path"
import { fileURLToPath } from "url"
import { taskStore, serverStore } from "../store.js"
import { getTaskBaseDir, getTaskCacheDir, getTaskConfigPath, getTaskConfigSync } from "../services/task-dir.js"
import { cacheGet, cacheSet, CACHE_TTL, swrJson, invalidateCache } from "../cache.js"
import { 
  getPDBData, 
  getDCDData, 
  getTrajectoryStatus, 
  getTrajectoryCacheDir,
  syncTrajectoryFiles,
  startTrajectorySync,
  stopTrajectorySync 
} from "../services/trajectory-sync.js"
import { loadAnalysisToCache } from "../services/analysis.js"
import { generateSimStatus } from "../services/sim-status-sync.js"
import { setConvergenceStopped } from "../services/convergence-stop.js"
import { runMain, spawnMain } from "../services/run-main.js"
import { loadMagnetomechToCache, runAndCacheMagnetomech, hasMagnetomechData, getMagnetomechImagePath } from "../services/magnetomech.js"

const REPO_ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..")

const HOME = process.env.HOME || "/home/selp"
// Interpreter override for commands whose per-task scripts need the conda env
// (e.g. convergence-check requires numpy + MDAnalysis).
const PYTHON_BIN = process.env.MD_PYTHON_BIN || join(HOME, ".local", "miniconda3", "envs", "igem2026", "bin", "python3")

const router = Router()

router.get("/sim-status", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  return swrJson(res, `simStatus:${taskId}`, CACHE_TTL.simStatus, async () => {
    const data = await generateSimStatus(taskId)
    try {
      const est = await runMain(taskId, "progress")
      if (est && est.overall) {
        data.estimated = est.overall
        data.overall.avg_progress_pct = est.overall.avg_progress_pct
        data.overall.est_remaining_h = est.overall.est_remaining_h
        data.overall.est_remaining_d = est.overall.est_remaining_d
      }
    } catch {}
    return data
  })
})

const hasStructureData = d => !!(d && (d.rg || d.e2e || d.rmsd || d.ss || d.energy || d.box || d.crosslink || d.chainRg))

router.get("/structure", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  return swrJson(res, `structure:${taskId}`, CACHE_TTL.structure, async () => {
    // Try loading from local analysis cache first.
    try {
      await loadAnalysisToCache(taskId)
      const localCached = cacheGet(`structure:${taskId}`, CACHE_TTL.structure)
      if (localCached && hasStructureData(localCached)) return localCached
    } catch {}

    // Fallback: fetch via the tasktype's main.py (structure command reads the
    // task's local/remote analysis/ files).
    const result = await runMain(taskId, "structure")
    return {
      source: "ssh",
      rg: result?.rg ?? null,
      e2e: result?.e2e ?? null,
      rmsd: result?.rmsd ?? null,
      ss: result?.ss ?? null,
      energy: result?.energy ?? null,
      box: result?.box ?? null,
      crosslink: result?.crosslink ?? null,
      crosslinkTable: result?.crosslinkTable ?? null,
      chainRg: result?.chainRg ?? null,
      meta: result?.meta ?? null,
    }
  }, hasStructureData)
})

router.get("/cluster", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  return swrJson(res, `cluster:${taskId}`, CACHE_TTL.cluster, async () => {
    // Tasktype's main.py reads its remote analysis/cluster_*.json files.
    const result = await runMain(taskId, "cluster")
    return {
      source: "ssh",
      clusters: result?.clusters ?? null,
      scatter: result?.scatter ?? null,
    }
  })
})

router.get("/checkpoint", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  return swrJson(res, `checkpoint:${taskId}`, CACHE_TTL.checkpoint, async () => {
    // Tasktype's main.py inspects its remote output/*.tcl + logs + processes.
    return runMain(taskId, "checkpoint")
  })
})

router.get("/magnetomech", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  return swrJson(res, `magnetomech:${taskId}`, CACHE_TTL.magnetomech, async () => {
    // Load from the task's cache/magnetomech/ artifacts (written by
    // main.py magnetomech); fall back to the tasktype's structure command.
    try {
      await loadMagnetomechToCache(taskId)
      const localCached = cacheGet(`magnetomech:${taskId}`, CACHE_TTL.magnetomech)
      if (localCached && hasMagnetomechData(localCached)) return localCached
    } catch {}
    const result = await runMain(taskId, "structure")
    return {
      source: "local",
      data: {
        summary: result?.summary ?? result?.data?.summary ?? null,
        curves: result?.curves ?? result?.data?.curves ?? null,
        layers: result?.layers ?? result?.data?.layers ?? null,
        config: result?.config ?? result?.data?.config ?? null,
      },
    }
  }, hasMagnetomechData)
})

// Static MATLAB 3D renders produced by code/plotResults.m into code/figures/.
// They are repo assets rather than per-task output, so they are served from
// their single source directory (no copies in the frontend bundle) and the
// filenames are allowlisted rather than interpolated into a path.
const MATLAB_FIGURES = {
  displacement: "Displacement_field.png",
  epsf: "Fiber_axial_strain_epsf.png",
  Ez: "Local_axial_modulus_E_z.png",
  porePressure: "Pore_pressure.png",
  stressSzz: "Stress_sigma_zz.png",
  magneticField: "Magnetic_field_H(x).png",
}

router.get("/matlab-figure/:key", (req, res) => {
  const file = MATLAB_FIGURES[req.params.key]
  if (!file) return res.status(404).json({ error: `unknown figure "${req.params.key}"` })
  const figPath = join(REPO_ROOT, "code", "figures", file)
  if (!existsSync(figPath)) return res.status(404).json({ error: "figure not generated yet (run the MATLAB plotResults)" })
  res.sendFile(figPath)
})

// Packed 32-chain precursor trajectory (flow-only 3D viewer).
const PACKING_DIR = "/home/selp/selp-packing"
const PACKING_FILES = new Set(["topo_protein.pdb", "traj_protein.xtc", "traj_protein.dcd", "construction.dcd", "film_topology.pdb", "film.dcd", "aa_fold_topology.pdb", "aa_fold.dcd", "aa_phase.dcd", "film_inplace.dcd"])
router.get("/packing/:file", (req, res) => {
  const file = req.params.file
  if (!PACKING_FILES.has(file)) return res.status(404).json({ error: "unknown packing file" })
  const p = join(PACKING_DIR, file)
  if (!existsSync(p)) return res.status(404).json({ error: "packing files not generated yet" })
  res.sendFile(p)
})

// The backend-rendered final simulation PNG (matplotlib/PIL, produced by
// code/magnetomech/run.py). Direct binary response so the frontend can show it
// as <img src="/api/data/magnetomech/image?taskId=...">.
router.get("/magnetomech/image", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  const imagePath = getMagnetomechImagePath(taskId)
  if (!existsSync(imagePath)) {
    return res.status(404).json({ error: "No rendered image for this task yet (run the computation first)" })
  }
  const { readFile } = await import("fs/promises")
  try {
    const data = await readFile(imagePath)
    res.setHeader("Content-Type", "image/png")
    res.setHeader("Content-Length", data.length)
    res.setHeader("Cache-Control", "no-store")
    return res.send(data)
  } catch (e) {
    return res.status(500).json({ error: String(e?.message ?? e) })
  }
})

router.post("/magnetomech/run", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  invalidateCache(taskId)
  try {
    const data = await runAndCacheMagnetomech(taskId)
    if (!data || !hasMagnetomechData(data)) {
      return res.status(500).json({ error: "magnetomech computation failed (no valid result)", detail: data })
    }
    return res.json({ ok: true, ...data })
  } catch (e) {
    return res.status(500).json({ error: String(e?.message ?? e) })
  }
})

router.post("/magnetomech/config", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  const numeric = (v, d) => (typeof v === "number" && Number.isFinite(v) ? v : d)
  const patch = req.body?.config ?? {}
  const next = {
    magnetomech: {
      modulusMode: patch.modulusMode ?? "affine",
      modulusKpa: typeof patch.modulusKpa === "number" && Number.isFinite(patch.modulusKpa) ? patch.modulusKpa : null,
      modulusPath: patch.modulusPath ?? null,
    },
    particle: {
      phi: numeric(patch.phi, 0.05),
      diameterNm: numeric(patch.diameterNm, 10.0),
      saturationAperM: numeric(patch.saturationAperM, 4.8e5),
    },
    field: {
      mode: patch.fieldMode ?? "uniform",
      maxT: numeric(patch.maxT, 0.6),
      heightMm: numeric(patch.heightMm, 10.0),
      nPoints: Math.max(3, Math.min(2001, Math.round(numeric(patch.nPoints, 201)))),
      gradientDeltaT: numeric(patch.gradientDeltaT, 0.2),
      csvPath: patch.csvPath ?? null,
    },
    temperatureK: numeric(patch.temperatureK, 310.0),
    coupling: Math.max(0, Math.min(1, numeric(patch.coupling, 0.25))),
    demagFactor: numeric(patch.demagFactor, 1 / 3),
  }
  const path = getTaskConfigPath(taskId)
  const prev = getTaskConfigSync(taskId) ?? {}
  const merged = { ...prev, ...next }
  try {
    const { writeFile } = await import("fs/promises")
    await writeFile(path, JSON.stringify(merged, null, 2) + "\n", "utf8")
  } catch (e) {
    return res.status(500).json({ error: String(e?.message ?? e) })
  }
  invalidateCache(taskId)
  return res.json({ ok: true, path, config: next })
})

// Legacy trajectory endpoint - redirects to new PDB endpoint
router.get("/trajectory", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  
  try {
    const pdbData = await getPDBData(taskId)
    if (pdbData) {
      res.setHeader("Content-Type", "chemical/x-pdb")
      return res.send(pdbData)
    }
    
    // Fallback to legacy generation (per-task main.py owns the remote script path)
    const task = taskStore.tasks.find(t => t.id === taskId)
    if (!task) return res.status(404).json({ error: "Task not found" })
    
    await runMain(taskId, "gen-trajectory", [
      "--output", join(task.workDir, "trajectory.pdb"),
      "--replica", "0",
    ], { timeout: 600000 })
    
    const pdbDataNew = await getPDBData(taskId)
    if (pdbDataNew) {
      res.setHeader("Content-Type", "chemical/x-pdb")
      return res.send(pdbDataNew)
    }
    
    res.status(404).json({ error: "No trajectory found" })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// Residue-level sequence annotations from input/sequences.csv + topology PDB.
// Standardized workflow: see backend/tasktype/tiger2/lib/sequence_annotation.py.
router.get("/sequence-annotations", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  try {
    const result = await runMain(taskId, "route", ["--route", "sequences"], { timeout: 30000 })
    if (result && result.ok === false) {
      return res.status(500).json({ error: result.error || "sequence annotation failed" })
    }
    res.json(result || { annotations: [] })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// New endpoint: reverse a task's structure back to its one-letter input sequence.
//
// For a TIGER2 task built from a prebuilt topology the sequence is recorded
// nowhere in its config or logs, so the PDB is the only source. Reads the same
// structure the viewer loads and reconstructs the per-chain sequence.
router.get("/sequence-from-pdb", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  try {
    const result = await runMain(taskId, "route", ["--route", "sequences", "--sub", "derive"], { timeout: 30000 })
    if (!result) return res.status(500).json({ error: "no result" })
    // A missing structure is a valid answer, not a server fault.
    if (result.ok === false) return res.status(404).json(result)
    res.json(result)
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// New endpoint: Serve PDB file
router.get("/pdb", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  
  try {
    const pdbData = await getPDBData(taskId)
    if (pdbData) {
      res.setHeader("Content-Type", "chemical/x-pdb")
      return res.send(pdbData)
    }
    res.status(404).json({ error: "PDB file not found" })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// New endpoint: Serve DCD file (binary)
router.get("/dcd", async (req, res) => {
  const { taskId, replica = "0" } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  
  try {
    const dcdData = await getDCDData(taskId, Number(replica))
    if (dcdData) {
      res.setHeader("Content-Type", "application/octet-stream")
      res.setHeader("Content-Length", dcdData.length)
      return res.send(dcdData)
    }
    res.status(404).json({ error: "DCD file not found" })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// DCD with .dcd extension in URL path for NGL.js format detection
// Filename format: {taskId}_rep{replica}.dcd
router.get("/dcd-file/:filename", async (req, res) => {
  const { filename } = req.params
  const baseName = filename.replace(/\.dcd$/, "")
  let taskId, replica

  const repMatch = baseName.match(/^(.+)_rep(\d+)$/)
  if (repMatch) {
    taskId = repMatch[1]
    replica = Number(repMatch[2])
  } else {
    taskId = baseName
    replica = 0
  }

  if (!taskId) return res.status(400).json({ error: "Invalid filename" })
  
  try {
    const dcdData = await getDCDData(taskId, replica)
    if (dcdData) {
      res.setHeader("Content-Type", "application/octet-stream")
      res.setHeader("Content-Length", dcdData.length)
      return res.send(dcdData)
    }
    res.status(404).json({ error: "DCD file not found" })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// Downsampled DCD preview (fast browser load). Falls back to the full merged
// trajectory when no preview has been generated yet.
router.get("/dcd-preview/:filename", async (req, res) => {
  const { filename } = req.params
  const baseName = filename.replace(/\.dcd$/, "")
  const repMatch = baseName.match(/^(.+)_rep(\d+)$/)
  const taskId = repMatch ? repMatch[1] : baseName
  const replica = repMatch ? Number(repMatch[2]) : 0

  if (!taskId) return res.status(400).json({ error: "Invalid filename" })

  try {
    const cacheDir = await getTrajectoryCacheDir(taskId)
    const previewPath = join(cacheDir, "preview", `replica_${replica}.dcd`)
    const { readFile } = await import("fs/promises")

    if (existsSync(previewPath)) {
      const data = await readFile(previewPath)
      res.setHeader("Content-Type", "application/octet-stream")
      res.setHeader("Content-Length", data.length)
      return res.send(data)
    }

    const dcdData = await getDCDData(taskId, replica)
    if (dcdData) {
      res.setHeader("Content-Type", "application/octet-stream")
      res.setHeader("Content-Length", dcdData.length)
      return res.send(dcdData)
    }
    res.status(404).json({ error: "DCD file not found" })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// Last-N-cycles DCD tail for the convergence page's detailed trajectory view
// (one DCD frame == one simulated cycle; generated by the tasktype route
// trajectory from the merged replica DCD). No fallback: the tail file is tiny
// and is regenerated on every sync.
router.get("/dcd-last100/:filename", async (req, res) => {
  const { filename } = req.params
  const baseName = filename.replace(/\.dcd$/, "")
  const repMatch = baseName.match(/^(.+)_rep(\d+)$/)
  const taskId = repMatch ? repMatch[1] : baseName
  const replica = repMatch ? Number(repMatch[2]) : 0

  if (!taskId) return res.status(400).json({ error: "Invalid filename" })

  try {
    const cacheDir = await getTrajectoryCacheDir(taskId)
    const tailPath = join(cacheDir, "last100", `replica_${replica}.dcd`)
    const { readFile } = await import("fs/promises")

    if (existsSync(tailPath)) {
      const data = await readFile(tailPath)
      res.setHeader("Content-Type", "application/octet-stream")
      res.setHeader("Content-Length", data.length)
      return res.send(data)
    }
    res.status(404).json({ error: "Last-100-cycles DCD not found" })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// New endpoint: Get trajectory sync status
router.get("/trajectory-status", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  
  try {
    const status = await getTrajectoryStatus(taskId)
    res.json(status)
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// New endpoint: Trigger trajectory sync
router.post("/trajectory-sync", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  
  try {
    const success = await syncTrajectoryFiles(taskId)
    const status = await getTrajectoryStatus(taskId)
    res.json({ success, status })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// New endpoint: Start periodic trajectory sync
router.post("/trajectory-sync/start", async (req, res) => {
  const { taskId, intervalMs = 60000 } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  
  try {
    startTrajectorySync(taskId, Number(intervalMs))
    res.json({ success: true, message: "Trajectory sync started" })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// New endpoint: Stop periodic trajectory sync
router.post("/trajectory-sync/stop", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  
  try {
    stopTrajectorySync(taskId)
    res.json({ success: true, message: "Trajectory sync stopped" })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// New endpoint: Start monitor daemon (background: NAMD + convergence loop)
router.post("/monitor/start", async (req, res) => {
  const { taskId } = req.body
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  const task = taskStore.tasks.find(t => t.id === taskId)
  if (!task) return res.status(404).json({ error: "Task not found" })
  if (!serverStore.servers.find(s => s.id === task.serverId)) {
    return res.status(404).json({ error: "Server not found" })
  }
  try {
    spawnMain(taskId, "monitor")
  } catch (e) {
    return res.status(500).json({ error: e.message })
  }
  await setConvergenceStopped(taskId, false)
  res.json({ ok: true, message: "Monitor started in background" })
})

// New endpoint: Monitor status
router.get("/monitor/status", async (req, res) => {
  const { taskId } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  try {
    const statePath = join(getTaskBaseDir(taskId), ".monitor_state.json")
    const { readFile } = await import("fs/promises")
    const content = await readFile(statePath, "utf8")
    res.json(JSON.parse(content))
  } catch {
    res.json({ started: false })
  }
})

// New endpoint: Check convergence (cached 10 min to avoid heavy DCD re-reads).
// `detectOnly=1` reports convergence without auto-stopping the simulation.
router.get("/convergence", async (req, res) => {
  const { taskId, detectOnly } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  const detectOnlyMode = detectOnly === "1" || detectOnly === "true"
  const refreshConvergence = async () => {
    // Always refresh cached trajectories before the check so the convergence
    // verdict reflects the latest simulation data (sync also refreshes DCDs
    // that already exist locally, not only missing ones).
    const trajDir = join(await getTaskCacheDir(taskId), "trajectory")
    try {
      const ok = await syncTrajectoryFiles(taskId)
      if (!ok && !existsSync(join(trajDir, "replica_0.dcd"))) {
        return { error: "No DCD trajectories available for this task. Trajectory sync could not find DCD files under the task working directory.", converged: false }
      }
    } catch (e) {
      if (!existsSync(join(trajDir, "replica_0.dcd"))) {
        throw new Error(`Trajectory sync failed: ${e.message}`)
      }
    }
    // Tasktype's main.py runs the local DCD-based convergence check
    // (per-task thresholds/layout come from the task's task_config.json).
    // The conda interpreter is used because that script needs numpy + MDAnalysis.
    const result = await runMain(taskId, "convergence-check", [], {
      interpreter: PYTHON_BIN,
      timeout: 120000,
      maxBuffer: 10 * 1024 * 1024,
    })
    // Optionally stop the simulation once both E2E and Rg have converged (all
    // replicas, required_stable_checks consecutive checks). Guarded by the
    // per-task `stopped` flag so the run is only terminated once per
    // convergence episode. In detect-only mode the simulation is never stopped.
    if (!detectOnlyMode && result.converged && !result.stopped) {
      try {
        console.log(`[Convergence] ${taskId} converged (E2E + Rg stable), stopping simulation...`)
        await runMain(taskId, "stop")
        result.stopped = true
        await setConvergenceStopped(taskId, true)
      } catch (e) {
        console.error(`[Convergence] ${taskId} stop failed: ${e.message}`)
      }
    }
    return result
  }
  return swrJson(res, `convergence:${taskId}`, 600000, refreshConvergence)
})

export default router
