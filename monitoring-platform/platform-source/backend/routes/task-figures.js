import { Router } from "express"
import { spawn } from "child_process"
import { existsSync } from "fs"
import { join } from "path"
import { taskStore } from "../store.js"
import { getTaskBaseDir } from "../services/task-dir.js"

const router = Router()
const PY = "/home/selp/venvs/wjx/bin/python"
const SCRIPT = "/home/selp/selp-figures/render_task.py"

function dirFor(task) {
  if (task.workDir && existsSync(task.workDir)) return task.workDir
  return getTaskBaseDir(task.id)
}

function cacheRoot(task) {
  const dir = join(getTaskBaseDir(task.id), "cache", "magnetomech")
  return existsSync(dir) ? dir : null
}

const renderCache = new Map()
const MAX_RENDERS = 3
let activeRenders = 0
const waitingRenders = []

function nextRender() {
  while (activeRenders < MAX_RENDERS && waitingRenders.length) {
    waitingRenders.shift()()
  }
}

function runPythonQueued(args) {
  return new Promise((resolve, reject) => {
    const start = () => {
      activeRenders += 1
      runPython(args).then(v => {
        activeRenders -= 1
        nextRender()
        resolve(v)
      }).catch(e => {
        activeRenders -= 1
        nextRender()
        reject(e)
      })
    }
    if (activeRenders < MAX_RENDERS) start()
    else waitingRenders.push(start)
  })
}

function runPython(args) {
  return new Promise((resolve, reject) => {
    const child = spawn(PY, [SCRIPT, ...args], { timeout: 120000 })
    const out = []
    const err = []
    child.stdout.on("data", d => out.push(d))
    child.stderr.on("data", d => err.push(d))
    child.on("error", reject)
    child.on("close", code => {
      if (code === 0) resolve(Buffer.concat(out))
      else reject(new Error(Buffer.concat(err).toString().slice(0, 600) || ("exit " + code)))
    })
  })
}

// GET /api/tasks/:id/figures -- list figures that can be recomputed from the
// task's current data directory.
router.get("/:id/figures", async (req, res) => {
  const task = taskStore.tasks.find(t => t.id === req.params.id)
  if (!task) return res.status(404).json({ error: "Task not found" })
  try {
    const extra = cacheRoot(task)
    const out = await runPython(["--list", dirFor(task), ...(extra ? [extra] : []), "--task-type", task.taskType || "", "--task-name", task.name || ""])
    res.type("application/json").send(out)
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// GET /api/tasks/:id/figures/:figure.svg -- render one figure on demand.
// Always recomputed from the files on disk; no cached image is stored.
router.get("/:id/figures/:figure.svg", async (req, res) => {
  const task = taskStore.tasks.find(t => t.id === req.params.id)
  if (!task) return res.status(404).json({ error: "Task not found" })
  if (!/^[a-z0-9-]{4,40}$/.test(req.params.figure)) {
    return res.status(400).json({ error: "Bad figure id" })
  }
  try {
    const key = task.id + ":" + req.params.figure
    const hit = renderCache.get(key)
    if (hit && Date.now() - hit.at < 30000) {
      return res.type("image/svg+xml; charset=utf-8").set("Cache-Control", "no-store").send(hit.svg)
    }
    const extra = cacheRoot(task)
    const svg = await runPythonQueued([dirFor(task), req.params.figure, ...(extra ? [extra] : []), "--task-type", task.taskType || "", "--task-name", task.name || ""])
    renderCache.set(key, { at: Date.now(), svg })
    if (renderCache.size > 400) {
      const oldest = [...renderCache.entries()].sort((a, b) => a[1].at - b[1].at).slice(0, 100)
      for (const [k] of oldest) renderCache.delete(k)
    }
    res.type("image/svg+xml; charset=utf-8").set("Cache-Control", "no-store").send(svg)
  } catch (e) {
    res.status(404).json({ error: e.message })
  }
})

export default router
