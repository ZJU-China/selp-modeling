import { taskStore, serverStore } from "./store.js"
import { getServerSession } from "./ssh.js"
import { cacheSet } from "./cache.js"
import { syncTrajectoryFiles } from "./services/trajectory-sync.js"
import { runAndCacheAnalysis } from "./services/analysis.js"
import { runMain, fallbackLogPrefix } from "./services/run-main.js"

let syncRunning = false

export async function syncAllTasks() {
  if (syncRunning) return
  syncRunning = true
  const connected = taskStore.tasks.filter(t => t.serverId && getServerSession(t.serverId))
  if (connected.length === 0) { syncRunning = false; return }
  try {
    const enrichedTasks = taskStore.tasks.map(t => ({
      ...t, password: undefined,
      serverName: serverStore.servers.find(s => s.id === t.serverId)?.name || "",
      connected: !!getServerSession(t.serverId),
    }))

    // Process/replica scan is owned by the shared tasktype's main.py (route
    // jobs), so the backend never touches the remote host directly. Run once
    // per cycle in parallel and collect all job groups before applying
    // checkpoint overrides.
    const allProcesses = [], allJobs = []
    const scanResults = await Promise.all(connected.map(async t => {
      const tLp = t.config?.logPrefix || fallbackLogPrefix(t.taskType)
      try {
        const scan = await runMain(t.id, "route", ["--route", "jobs"], { timeout: 60000 })
        return { t, tLp, scan }
      } catch { return null }
    }))
    for (const r of scanResults) {
      if (!r || !r.scan) continue
      allProcesses.push(...(r.scan.processes || []))
      const taskProcesses = (r.scan.processes || []).filter(p => p.command.includes(r.tLp))
      const jobGroup = { config: `${r.tLp}.conf`, processes: taskProcesses, replicas: r.scan.replicas || {}, running: taskProcesses.length > 0, taskId: r.t.id, taskName: r.t.name }
      allJobs.push(jobGroup)
    }

    // Per-task checkpoint/status/structure/cluster are all task-specific and
    // owned by the shared tasktype's main.py, so delegate to runMain. The
    // checkpoint knows about cluster/slurm runs (log freshness) and its running
    // flag is authoritative for the task's job group.
    for (const t of connected) {
      try {
        const cp = await runMain(t.id, "checkpoint")
        if (cp) {
          cacheSet(`checkpoint:${t.id}`, cp)
          const job = allJobs.find(j => j.taskId === t.id)
          if (job && typeof cp.running === "boolean") job.running = cp.running
        }
      } catch (e) {
        console.warn(`[Sync] checkpoint ${t.id}: ${e.message}`)
      }

      try {
        const st = await runMain(t.id, "structure")
        if (st) cacheSet(`structure:${t.id}`, { source: "ssh", ...st })
      } catch (e) {
        console.warn(`[Sync] structure ${t.id}: ${e.message}`)
      }

      try {
        const cl = await runMain(t.id, "cluster")
        if (cl) cacheSet(`cluster:${t.id}`, { source: "ssh", ...cl })
      } catch (e) {
        console.warn(`[Sync] cluster ${t.id}: ${e.message}`)
      }
    }

    cacheSet("tasks", { processes: allProcesses, jobs: allJobs, taskConfigs: enrichedTasks })
  } catch (e) { console.error("[Sync] Error:", e.message) }
  finally { syncRunning = false }
}

let trajSyncInterval = null

export function startSync() {
  setInterval(syncAllTasks, 8000)
  // Periodic trajectory DCD sync every 5 minutes + analysis
  trajSyncInterval = setInterval(async () => {
    for (const task of taskStore.tasks) {
      if (!task.serverId || !getServerSession(task.serverId)) continue
      try {
        await syncTrajectoryFiles(task.id)
        await runAndCacheAnalysis(task.id)
      } catch (e) { console.error(`[Sync] Traj/analysis error for ${task.id}: ${e.message}`) }
    }
  }, 300000)

  // Initial analysis run for all connected tasks
  setTimeout(async () => {
    for (const task of taskStore.tasks) {
      if (!task.serverId || !getServerSession(task.serverId)) continue
      try { await runAndCacheAnalysis(task.id) } catch (e) { console.warn(`[Sync] Initial analysis ${task.id}: ${e.message}`) }
    }
  }, 15000)
}
