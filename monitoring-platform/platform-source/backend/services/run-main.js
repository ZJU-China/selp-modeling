import { execFile, spawn } from "child_process"
import { join } from "path"
import { existsSync } from "fs"
import { taskStore, serverStore, isLocalTask } from "../store.js"
import { getTaskBaseDir, getTaskConfigPath, getTaskScriptsDir } from "./task-dir.js"

// Legacy tasks (no task_config.json) don't record their own logPrefix; fall
// back to the task type's own name (the conventional prefix for that type)
// instead of a hardcoded "tiger2".
export function fallbackLogPrefix(taskType) {
  return taskType || "tiger2"
}

function buildMainArgs(taskId, command, extraArgs = [], opts = {}) {
  const task = taskStore.tasks.find(t => t.id === taskId)
  if (!task) throw new Error("Task not found")
  const local = isLocalTask(task)
  // Local task types run in-process on this machine, so a serverId on one is
  // stale/leftover metadata rather than a target to connect to. Resolving it
  // anyway would append --host/--password and make a local run need SSH.
  const server = local ? null : serverStore.servers.find(s => s.id === task.serverId)
  if (!server && !local) throw new Error("Server not found")

  const key = server?.privateKey || ""
  const cfg = task.config || {}
  const configPath = getTaskConfigPath(taskId)
  const args = [
    join(getTaskScriptsDir(taskId, task.taskType), "main.py"), command,
  ]
  if (server) {
    args.push(
      "--host", server.host,
      "--port", String(server.port),
      "--user", server.username,
      ...(key ? ["--key", key] : []),
      ...(server.password && !key ? ["--password", server.password] : []),
    )
  }
  args.push("--local-dir", getTaskBaseDir(taskId))
  if (existsSync(configPath)) {
    // Shared tasktype main.py: task-specific values come from task_config.json.
    args.push("--task-config", configPath)
  } else {
    // Legacy fallback: a task without task_config.json gets its specifics as
    // CLI flags (old per-task scripts are then expected to exist).
    args.push(
      "--remote-dir", task.workDir,
      "--log-prefix", cfg.logPrefix || fallbackLogPrefix(task.taskType),
    )
    if (cfg.numReplicas) args.push("--num-replicas", String(cfg.numReplicas))
    if (cfg.stepsPerCycle) args.push("--steps-per-cycle", String(cfg.stepsPerCycle))
    if (cfg.totalCycles) args.push("--total-cycles", String(cfg.totalCycles))
  }
  if (server?.namdBin) args.push("--namd-bin", server.namdBin)
  args.push(...extraArgs)

  return { bin: opts.interpreter || "python3", args }
}

// Run the shared tasktype's main.py command. All task-specific judgments
// (specific tasks, processes, file strings) come from the task's own
// task_config.json. Resolves with parsed JSON, or { raw } when stdout is not JSON.
export function runMain(taskId, command, extraArgs = [], opts = {}) {
  let built
  try { built = buildMainArgs(taskId, command, extraArgs, opts) }
  catch (e) { return Promise.reject(e) }
  return new Promise((resolve, reject) => {
    execFile(built.bin, built.args, {
      timeout: opts.timeout ?? 120000,
      maxBuffer: opts.maxBuffer ?? 10 * 1024 * 1024,
    }, (err, stdout, stderr) => {
      if (err) return reject(new Error(stderr?.slice(0, 1000) || err.message))
      try { resolve(JSON.parse(stdout)) }
      catch { resolve({ raw: stdout.trim() }) }
    })
  })
}

// Spawn a task's own main.py command detached (e.g. long-running monitor).
export function spawnMain(taskId, command, extraArgs = [], opts = {}) {
  const built = buildMainArgs(taskId, command, extraArgs, opts)
  const child = spawn(built.bin, built.args, {
    stdio: ["ignore", "pipe", "pipe"],
    detached: true,
  })
  child.unref()
  return child
}
