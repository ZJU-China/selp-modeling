import { join, dirname, normalize, relative, isAbsolute } from "path"
import { fileURLToPath } from "url"
import { mkdir, writeFile } from "fs/promises"
import { existsSync, readFileSync } from "fs"

const __dirname = dirname(fileURLToPath(import.meta.url))
const TASKS_DIR = process.env.TASKS_DIR || join(__dirname, "..", "tasks")
const TASKTYPE_DIR = join(__dirname, "..", "tasktype")

export function getTaskBaseDir(taskId) {
  return join(TASKS_DIR, taskId)
}

export async function ensureTaskDirs(taskId, ...subs) {
  const base = getTaskBaseDir(taskId)
  for (const sub of subs) {
    await mkdir(join(base, sub), { recursive: true })
  }
  return base
}

export function getTaskInputDir(taskId) {
  return join(TASKS_DIR, taskId, "input")
}

export function getTaskLogsDir(taskId) {
  return join(TASKS_DIR, taskId, "logs")
}

export function getTaskOutputDir(taskId) {
  return join(TASKS_DIR, taskId, "output")
}

export function getTaskCacheDir(taskId) {
  return join(TASKS_DIR, taskId, "cache")
}

// Resolve the directory holding a task's main.py/analyze.py/gen_sim_status.py.
// Prefers the shared tasktype/<taskType> tree; falls back to the task's own
// per-task scripts/ dir (for tasks created via the UI that predate the
// tasktype consolidation and never got a shared type).
export function getTaskScriptsDir(taskId, taskType) {
  if (taskType) {
    const shared = getTaskTypeScriptsDir(taskType)
    if (existsSync(shared)) return shared
  }
  return join(TASKS_DIR, taskId, "scripts")
}

export function getTaskConfigDir(taskId) {
  return join(TASKS_DIR, taskId, "config")
}

export function getTaskTypeDir() {
  return TASKTYPE_DIR
}

// Tasktype aliases: variants that share the same scripts tree as another type
// (tiger2-convergence is the TIGER2 convergent-sampling machinery re-exported
// for UI-created tasks of that type).
const TASKTYPE_ALIASES = { "tiger2-convergence": "tiger2" }

export function getTaskTypeScriptsDir(taskType) {
  return join(TASKTYPE_DIR, TASKTYPE_ALIASES[taskType] || taskType || "tiger2")
}

export function getTaskConfigPath(taskId) {
  return join(TASKS_DIR, taskId, "scripts", "task_config.json")
}

// Parse the task's own task_config.json (returns null when absent/invalid).
export function getTaskConfigSync(taskId) {
  try {
    return JSON.parse(readFileSync(getTaskConfigPath(taskId), "utf8"))
  } catch {
    return null
  }
}

// Merge the store's task.config into scripts/task_config.json so that a shared
// tasktype's `main.py --task-config` sees exactly what the UI saved.
//
// The store is authoritative and the file is what the Python side reads, so the
// two drifting apart is how an edited sequence silently re-runs the previous
// structure. Anything writing task.config must go through here.
export async function persistTaskConfig(taskId, config) {
  if (!config || typeof config !== "object" || Object.keys(config).length === 0) return null
  const cfgPath = getTaskConfigPath(taskId)
  let onDisk = {}
  try { onDisk = JSON.parse(readFileSync(cfgPath, "utf8")) } catch {}
  const merged = deepMerge(onDisk, config)
  await writeFile(cfgPath, JSON.stringify(merged, null, 2) + "\n", "utf8")
  return merged
}

function deepMerge(base, override) {
  if (!override || typeof override !== "object") return base
  const out = { ...base }
  for (const [k, v] of Object.entries(override)) {
    if (v === undefined) continue
    out[k] = v && typeof v === "object" && !Array.isArray(v) ? deepMerge(base?.[k] || {}, v) : v
  }
  return out
}

// Quick-create channel: scaffold <taskId>/scripts/task_config.json from the
// tasktype's task_config.template.json (the single default template every
// task type ships, e.g. backend/tasktype/tiger2/task_config.template.json).
//
// This is the ONLY thing that distinguishes a UI/API-created task from one
// set up entirely by hand (mkdir + write task_config.json + edit tasks.json):
// both end up with the exact same file at the exact same path, which is all
// getTaskScriptsDir/runMain ever look for. So it never overwrites an
// existing config — a task that already has one (hand-authored, or scaffolded
// by an earlier call) is left untouched; this keeps both creation paths
// fully interchangeable and safe to call unconditionally.
export async function scaffoldTaskConfig(taskId, taskType, overrides = {}) {
  const configPath = getTaskConfigPath(taskId)
  if (existsSync(configPath)) return { created: false, path: configPath }

  const templatePath = join(getTaskTypeScriptsDir(taskType), "task_config.template.json")
  let template = {}
  try { template = JSON.parse(readFileSync(templatePath, "utf8")) } catch {}
  const { _comment, ...rest } = template

  const data = deepMerge(rest, overrides)
  await ensureTaskDirs(taskId, "scripts", "input", "logs", "cache")
  await writeFile(configPath, JSON.stringify(data, null, 2) + "\n")
  return { created: true, path: configPath, usedTemplate: !!Object.keys(rest).length }
}

// Resolve a path inside a task directory, refusing anything that escapes it.
// Shared so every route that touches task files applies the same check rather
// than each carrying its own copy.
export function resolveTaskPath(taskId, p) {
  const base = getTaskBaseDir(taskId)
  const target = normalize(join(base, p || "."))
  const rel = relative(base, target)
  if (rel.startsWith("..") || isAbsolute(rel)) {
    throw new Error("path escapes task directory")
  }
  return { base, target, rel }
}
