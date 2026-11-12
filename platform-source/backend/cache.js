import { join, dirname } from "path"
import { fileURLToPath } from "url"
import { mkdir, readFile, writeFile, rename, unlink, readdir } from "fs/promises"

const __dirname = dirname(fileURLToPath(import.meta.url))
const CACHE_DIR = process.env.CACHE_DIR || join(__dirname, ".cache")

// In-memory cache (runtime), with a write-through copy on disk so a backend
// restart (or a browser refresh after one) can serve the last computed result
// instantly instead of re-running SSH/analysis.
const dataCache = new Map()

// TTLs (ms) per cache key. Every entry can be overridden via environment:
// MD_CACHE_TTL_TASKS, MD_CACHE_TTL_SIMSTATUS, _CHECKPOINT, _STRUCTURE,
// _CLUSTER, _MAGNETOMECH (or the named `tasks`/`simStatus`/... keys).
const ttlEnv = (name, fallback) => {
  const v = process.env[`MD_CACHE_TTL_${name.toUpperCase()}`] ?? process.env[name]
  return v ? Number(v) : fallback
}
export const CACHE_TTL = {
  tasks: ttlEnv("tasks", 8000),
  simStatus: ttlEnv("simStatus", 30000),
  checkpoint: ttlEnv("checkpoint", 10000),
  structure: ttlEnv("structure", 60000),
  cluster: ttlEnv("cluster", 60000),
  magnetomech: ttlEnv("magnetomech", 60000),
}

function diskPath(key) {
  return join(CACHE_DIR, key.replace(/[^A-Za-z0-9_.-]/g, "_") + ".json")
}

export function cacheGet(key, ttlMs) {
  const entry = dataCache.get(key)
  if (entry && Date.now() - entry.time < ttlMs) return entry.data
  return null
}

// Stale-while-revalidate: return the last known value regardless of age
// (null when nothing has ever been cached for this key).
export function cacheGetStale(key) {
  const entry = dataCache.get(key)
  return entry ? entry.data : null
}

export function cacheSet(key, data) {
  dataCache.set(key, { data, time: Date.now() })
  void persist(key, data)
}

export function invalidateCache(taskId) {
  for (const key of [...dataCache.keys()]) {
    if (key === taskId || key.endsWith(`:${taskId}`)) {
      dataCache.delete(key)
      void unlink(diskPath(key)).catch(() => {})
    }
  }
  dataCache.delete("tasks")
  void unlink(diskPath("tasks")).catch(() => {})
}

// Soft-invalidate: keep the last known value but mark it stale so the next
// swrJson call serves it immediately and revalidates in the background.
// A hard delete ("tasks") would force a synchronous cold recompute on the
// next GET, which runs a serial SSH scan of every connected task and can
// block the response for tens of seconds.
export function expireCache(key) {
  const entry = dataCache.get(key)
  if (entry) entry.time = 0
}

// SWR endpoint helper: serve a fresh cached value immediately; on a stale
// cache serve the old value right away and revalidate in the background; on a
// cold cache compute synchronously. `refresh` must return the value to cache
// (it may cacheSet itself; swrJson will also store whatever it returns).
// `isValid` (optional) lets the caller reject cached values that are empty or
// useless (e.g. all-null structure results) so they are recomputed.
export async function swrJson(res, key, ttlMs, refresh, isValid) {
  const valid = isValid || (() => true)
  const fresh = cacheGet(key, ttlMs)
  if (fresh !== null && valid(fresh)) return res.json(fresh)

  const stale = cacheGetStale(key)
  if (stale !== null && valid(stale)) {
    res.json(stale)
    void refresh()
      .then(data => { if (data !== undefined && data !== null) cacheSet(key, data) })
      .catch(() => {})
    return
  }

  try {
    const data = await refresh()
    if (data !== undefined && data !== null) cacheSet(key, data)
    res.json(data)
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
}

async function persist(key, data) {
  try {
    await mkdir(CACHE_DIR, { recursive: true })
    const path = diskPath(key)
    const tmp = path + ".tmp"
    await writeFile(tmp, JSON.stringify({ key, time: Date.now(), data }), "utf8")
    await rename(tmp, path)
  } catch {}
}

// Warm the in-memory cache from disk on startup so cold starts are instant.
async function warmUp() {
  try {
    await mkdir(CACHE_DIR, { recursive: true })
    for (const f of await readdir(CACHE_DIR)) {
      if (!f.endsWith(".json") || f.endsWith(".tmp")) continue
      try {
        const raw = JSON.parse(await readFile(join(CACHE_DIR, f), "utf8"))
        if (raw && typeof raw.key === "string" && typeof raw.time === "number") {
          dataCache.set(raw.key, { data: raw.data, time: raw.time })
        }
      } catch {}
    }
  } catch {}
}
await warmUp()
