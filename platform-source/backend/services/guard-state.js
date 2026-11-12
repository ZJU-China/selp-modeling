// Persistent state + event log for the task guard. Stored in a git-ignored
// JSON under backend/guard-state.json so the guard survives backend restarts
// (cooldowns, pause flags, event history) without touching git.
import { readFile, writeFile } from "fs/promises"
import { existsSync } from "fs"
import { dirname, join } from "path"
import { fileURLToPath } from "url"

const __dirname = dirname(fileURLToPath(import.meta.url))
export const GUARD_STATE_PATH =
  process.env.MD_GUARD_STATE || join(__dirname, "..", "guard-state.json")
const MAX_EVENTS = 500

let cache = null

async function read() {
  if (cache) return cache
  try {
    if (existsSync(GUARD_STATE_PATH)) {
      cache = JSON.parse(await readFile(GUARD_STATE_PATH, "utf8"))
    }
  } catch {}
  cache = cache || {
    version: 1,
    globalPaused: false,
    tasks: {},   // taskId -> { paused, cooldownUntil, restartCount, lastEventAt }
    events: [],  // newest first
  }
  return cache
}

async function persist() {
  try {
    await writeFile(GUARD_STATE_PATH, JSON.stringify(cache, null, 2))
  } catch (e) {
    console.error(`[Guard] persist state: ${e.message}`)
  }
}

function now() {
  return Date.now()
}

// ---- task flags -----------------------------------------------------------

export async function isTaskPaused(taskId) {
  const s = await read()
  return !!(s.globalPaused || s.tasks[taskId]?.paused)
}

export async function setTaskPaused(taskId, paused) {
  const s = await read()
  s.tasks[taskId] = { ...(s.tasks[taskId] || {}), paused: !!paused }
  await persist()
}

export async function setGlobalPaused(paused) {
  const s = await read()
  s.globalPaused = !!paused
  await persist()
}

export async function bumpRestartCount(taskId) {
  const s = await read()
  const t = s.tasks[taskId] || {}
  s.tasks[taskId] = {
    ...t,
    restartCount: (t.restartCount || 0) + 1,
    lastEventAt: now(),
  }
  await persist()
  return s.tasks[taskId].restartCount
}

export function getCooldownUntil(taskId) {
  return cache?.tasks?.[taskId]?.cooldownUntil || 0
}

export async function setCooldownUntil(taskId, ts) {
  const s = await read()
  s.tasks[taskId] = { ...(s.tasks[taskId] || {}), cooldownUntil: ts }
  await persist()
}

// ---- LLM classify throttling ---------------------------------------------
// Remember when we last ran an LLM classification for a task so the guard can
// avoid re-classifying the same repeated failure on every cycle. Only persisted
// in memory in-memory is fine across restarts is handled by doing it cheap; we
// keep it in the persisted state so a restart doesn't immediately re-classify.

export function getLastClassify(taskId) {
  return cache?.tasks?.[taskId]?.lastClassify || null
}

export async function setLastClassify(taskId, decision, reason) {
  const s = await read()
  s.tasks[taskId] = {
    ...(s.tasks[taskId] || {}),
    lastClassify: { at: now(), decision, reason },
  }
  await persist()
}

// ---- event log ------------------------------------------------------------

export async function appendEvent(evt) {
  const s = await read()
  s.events.unshift({
    id: `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    at: now(),
    ...evt,
  })
  if (s.events.length > MAX_EVENTS) s.events.length = MAX_EVENTS
  const t = (s.tasks[evt.taskId] = { ...(s.tasks[evt.taskId] || {}), lastEventAt: now() })
  await persist()
  return s.events[0]
}

export async function getGuardState() {
  const s = await read()
  return {
    globalPaused: s.globalPaused,
    tasks: s.tasks,
    events: s.events.slice(0, 200),
  }
}
