// AI task guard: monitors tasks for unexpected failures and, when detected,
// uses the configured local LLM to decide whether to auto-recover (restart a
// TIGER2 replica from its checkpoint) or report the failure as un-recoverable.
//
// Unlike the passive 8s sync loop, this guard maintains per-task intent so it
// can tell a user-initiated stop (start/stop/continue/restart/pause via the
// control routes, which call markUserIntent()) apart from a process that died
// on its own.
//
// Integrated into the backend service (started from index.js) — no separate
// process.
import { readFile, readdir } from "fs/promises"
import { createWriteStream } from "fs"
import { join } from "path"
import { taskStore } from "../store.js"
import { runMain } from "./run-main.js"
import { getTaskBaseDir, getTaskLogsDir } from "./task-dir.js"
import { complete } from "./llm-client.js"
import {
  isTaskPaused,
  setCooldownUntil,
  getCooldownUntil,
  bumpRestartCount,
  appendEvent,
  getLastClassify,
  setLastClassify,
} from "./guard-state.js"

const MONITORED_TYPES = new Set(["tiger2", "gromacs_cg"])
const RESTARTABLE_TYPES = new Set(["tiger2", "tiger2-convergence"])

// Throttle LLM classification so a persistently-failing task is not re-sent to
// the model on every 60s pass. Default: re-classify the same failure at most
// once every 2 hours. Override with MD_GUARD_LLM_INTERVAL_MS.
const LLM_CLASSIFY_INTERVAL_MS = Number(process.env.MD_GUARD_LLM_INTERVAL_MS) || 2 * 60 * 60 * 1000

// printf log the guard lifecycle to a file for offline forensics.
const LOG_FILE = process.env.MD_GUARD_LOG || "/tmp/md-guard.log"
let logHandle = null

function glog(msg) {
  const line = `[${new Date().toISOString()}] ${msg}`
  console.log(`[Guard] ${msg}`)
  try {
    if (!logHandle) logHandle = createWriteStream(LOG_FILE, { flags: "a" })
    logHandle.write(line + "\n")
  } catch {}
}

// ---- user intent ----------------------------------------------------------
// Per-task map of taskId -> timestamp of the last user-initiated control
// action. Set by the control routes (start/stop/continue/restart/pause). The
// guard treats a running->stopped transition within this window as intended.
const userIntent = new Map()
const USER_INTENT_WINDOW_MS = 3 * 60 * 1000

export function markUserIntent(taskId) {
  userIntent.set(taskId, Date.now())
}

export function clearUserIntent(taskId) {
  userIntent.delete(taskId)
}

function isUserIntentRecent(taskId) {
  const t = userIntent.get(taskId)
  return t && Date.now() - t < USER_INTENT_WINDOW_MS
}

// ---- log scanning ---------------------------------------------------------

// Normalise per-task log layout into a list of absolute local log paths.
async function collectLogFiles(taskId) {
  const files = []
  const roots = [join(getTaskBaseDir(taskId), "logs"), join(getTaskBaseDir(taskId), "cache")]
  for (const dir of roots) {
    let entries
    try { entries = await readdir(dir, { withFileTypes: true }) } catch { continue }
    for (const sub of entries) {
      const sp = join(dir, sub.name)
      if (sub.isDirectory()) {
        let inner
        try { inner = await readdir(sp, { withFileTypes: true }) } catch { continue }
        for (const e of inner) {
          if (/\.(log|out|err)$/.test(e.name)) files.push(join(sp, e.name))
        }
      } else if (/\.(log|out|err)$/.test(sub.name)) {
        files.push(sp)
      }
    }
  }
  return files
}

const ERROR_PATTERNS = [
  /FATAL ERROR/i, /\bERROR\s*(:|occurred|encountered)/i, /TCL:\s+\S+.*error/i, /\bNaN\b/,
  /Segmentation fault/i, /fatal error/i, /can't open/i, /file not found/i,
  /Exceeded maximum/i, /out of memory/i, /\bKilled\b/i, /exited with/i,
]

// Detect whether a task is (or recently was) in an error state by tailing its
// local synced logs. Returns { failed, snippet, matched } where snippet is the
// tail passed to the LLM for classification.
async function scanErrorLogs(taskId) {
  const files = await collectLogFiles(taskId)
  if (files.length === 0) return { failed: false, snippet: "" }
  let snippet = ""
  let matched = null
  // Consider the newest file first; gather tails until we have a snippet.
  for (const f of files.slice(0, 6)) {
    let content = ""
    try { content = await readFile(f, "utf8") } catch { continue }
    if (!content.trim()) continue
    for (const pat of ERROR_PATTERNS) {
      if (pat.test(content)) { matched = matched || pat.source; break }
    }
    const tail = content.slice(-4000)
    snippet = snippet ? tail + "\n---\n" + snippet : tail
    if (snippet.length >= 4000) break
  }
  return { failed: !!matched, snippet: snippet.slice(0, 4000), matched }
}

// ---- LLM classification ---------------------------------------------------
// Ask the model, given the log tail + task context, to return a JSON decision
// choosing one of: restart (auto-recoverable), report (cannot auto-fix), or
// no_action (log doesn't show a real failure).
const PROMPT = (taskName, taskType, snippet) => `You are an automated NAMD/GROMACS simulation guard.
A task just stopped unexpectedly. Decide whether it is safe to auto-restart from its last checkpoint.

Task name: ${taskName}
Task type: ${taskType}

Log tail (may be partial or contain several logs):
=====
${snippet || "(no log content available)"}
=====

Consider:
- restart: transient/recoverable errors where resuming from checkpoint is safe,
  e.g. node failure, OOM, network hiccup, MPI rank died but inputs intact.
- report: hard errors that cannot heal on their own and need human attention,
  e.g. bad parameters, corrupted force field files, persistent NaN, topology errors.
- no_action: the log does not actually show a failure (e.g. it is empty, only a
  normal shutdown, or a user stop).

Reply with ONLY a JSON object, no prose:
{"decision":"restart|report|no_action","reason":"<short justification in English>","safe_to_restart":true|false}`

async function classifyFailure(task, snippet) {
  const maxAttempts = 3
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const raw = await complete({
        json: true,
        temperature: 0.1,
        maxTokens: 512,
        messages: [
          { role: "system", content: "You return JSON only." },
          { role: "user", content: PROMPT(task.name, task.taskType, snippet) },
        ],
      })
      const parsed = JSON.parse(raw.trim())
      if (!parsed || typeof parsed !== "object") {
        throw new Error("empty JSON object")
      }
      const decision = ["restart", "report", "no_action"].includes(parsed.decision)
        ? parsed.decision
        : "report"
      return { decision, reason: parsed.reason || raw.slice(0, 200) }
    } catch (e) {
      // Retry on malformed/non-JSON LLM output (common right after the model
      // wakes from an idle VRAM-unload: the first completion is often truncated
      // or mixed with reasoning text). A second call is cheap and usually clean.
      glog(`classify ${task.name}: attempt ${attempt} bad LLM output (${e.message}); retrying`)
      if (attempt === maxAttempts) {
        // Model unavailable / consistently malformed -> fail safe: report.
        return { decision: "report", reason: `LLM unavailable (${e.message}); gave up safely` }
      }
    }
  }
  return { decision: "report", reason: "LLM unavailable; gave up safely" }
}

// ---- recovery -------------------------------------------------------------

async function attemptRestart(taskId) {
  const result = await runMain(taskId, "restart", [], { timeout: 180000 })
  return result
}

// ---- main evaluation ------------------------------------------------------

// Detect one candidate failed task and take the appropriate action.
export async function guardTask(taskId) {
  const task = taskStore.tasks.find(t => t.id === taskId)
  if (!task) return { status: "skip", reason: "task not found" }

  const type = task.taskType
  if (task.config?.guard === "off") return { status: "skip", reason: "guard disabled per task" }
  if (await isTaskPaused(taskId)) return { status: "skip", reason: "paused" }
  if (Date.now() < getCooldownUntil(taskId)) return { status: "skip", reason: "in cooldown" }
  if (isUserIntentRecent(taskId)) return { status: "skip", reason: "recent user action" }

  let running
  let snippet = ""
  try {
    const st = await runMain(taskId, "status", [], { timeout: 60000 })
    running = st?.running
  } catch {
    return { status: "skip", reason: "status unavailable (ssh?)" }
  }

  // Only act when we can conclusively see the process is down.
  if (running) return { status: "ok", reason: "running" }

  const scan = await scanErrorLogs(taskId)
  snippet = scan.snippet

  // No error signature found + process down. If user stopped recently, skip;
  // otherwise it may just be a normal finish — only land a "report" event when
  // there's an actual error signature. Don't auto-restart on ambiguous cases.
  if (!scan.failed) {
    return { status: "ok", reason: "stopped but no error signature found" }
  }

  // Only the types we explicitly monitor get LLM + auto-recovery.
  if (!MONITORED_TYPES.has(type)) {
    await appendEvent({
      taskId, taskName: task.name, taskType: type,
      level: "warn", action: "report", source: "guard",
      message: `Unexpected failure detected (${scan.matched})`,
    })
    return { status: "reported", reason: scan.matched }
  }

  // Throttled LLM classification: only hit the model once per
  // LLM_CLASSIFY_INTERVAL_MS for a task that keeps failing. Reuse the last
  // decision in between so a repeated failure doesn't re-trigger the model
  // (and a possible restart) on every 60s pass.
  const last = getLastClassify(taskId)
  let classified
  let reused = false
  if (last && Date.now() - last.at < LLM_CLASSIFY_INTERVAL_MS) {
    glog(`classify ${task.name}: throttled, reusing ${last.decision} (${last.reason})`)
    classified = { decision: last.decision, reason: last.reason }
    reused = true
  } else {
    classified = await classifyFailure(task, snippet)
    glog(`classify ${task.name}: ${classified.decision} (${classified.reason})`)
    await setLastClassify(taskId, classified.decision, classified.reason)
  }

  const decision = classified.decision

  if (decision === "no_action") {
    return { status: "ok", reason: "llm: no real failure" }
  }

  if (decision === "report" || !RESTARTABLE_TYPES.has(type)) {
    // Only log a fresh event on the pass that actually classified; a throttled
    // reuse just re-confirms the earlier outcome without spamming the event log.
    if (!reused) {
      await appendEvent({
        taskId, taskName: task.name, taskType: type,
        level: "error", action: "report", source: "guard",
        decision, reason: classified.reason,
        message: `Failed; not auto-recoverable: ${classified.reason}`,
      })
    }
    await setCooldownUntil(taskId, Date.now() + 30 * 60 * 1000)
    return { status: "reported", reason: classified.reason }
  }

  // decision === "restart": auto-restart from checkpoint.
  try {
    const restartCount = await bumpRestartCount(taskId)
    const res = await attemptRestart(taskId)
    const ok = res?.running !== false && !res?.error
    await appendEvent({
      taskId, taskName: task.name, taskType: type,
      level: ok ? "info" : "error", action: ok ? "restarted" : "restart_failed",
      source: "guard", decision, reason: classified.reason,
      restartCount,
      message: ok
        ? `Auto-restarted from checkpoint (attempt ${restartCount})`
        : `Auto-restart attempt ${restartCount} did not confirm running`,
    })
    if (!ok) {
      await setCooldownUntil(taskId, Date.now() + 15 * 60 * 1000)
      return { status: "restart_failed", reason: res?.error || "not running after restart" }
    }
    clearUserIntent(taskId)
    return { status: "restarted", restartCount, reason: classified.reason }
  } catch (e) {
    const restartCount = await bumpRestartCount(taskId)
    await appendEvent({
      taskId, taskName: task.name, taskType: type,
      level: "error", action: "restart_failed", source: "guard",
      decision, reason: e.message, restartCount,
      message: `Restart threw: ${e.message}`,
    })
    await setCooldownUntil(taskId, Date.now() + 15 * 60 * 1000)
    return { status: "restart_failed", reason: e.message }
  }
}

// Run one full pass over all tasks (called on the guard's interval).
export async function guardAllTasks() {
  const tasks = taskStore.tasks
    .filter(t => t.serverId)
  const results = {}
  for (const t of tasks) {
    try {
      results[t.id] = await guardTask(t.id)
    } catch (e) {
      results[t.id] = { status: "error", reason: e.message }
    }
  }
  return results
}

let interval = null

export function startGuard(intervalMs = 60000) {
  if (interval) clearInterval(interval)
  glog(`guard started (interval ${intervalMs}ms)`)
  interval = setInterval(async () => {
    try { await guardAllTasks() } catch (e) { glog(`guard pass error: ${e.message}`) }
  }, intervalMs)
  return interval
}
