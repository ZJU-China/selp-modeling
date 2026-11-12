import { Router } from "express"
import { join, dirname } from "path"
import { readdir, readFile, writeFile, mkdir, rm, stat } from "fs/promises"
import { getTaskBaseDir, ensureTaskDirs, resolveTaskPath } from "../services/task-dir.js"

const router = Router()

// The file browser browses the backend's own per-task directory
// (backend/tasks/<taskId>/input, logs, output) — not the remote simulation
// server. Every path is resolved relative to the task's base dir and is
// rejected if it escapes it.
async function listDir(dir) {
  const entries = await readdir(dir, { withFileTypes: true })
  // stat() follows symlinks, so flow-<prevId> input links resolve to their
  // target and show up as navigable directories.
  const meta = await Promise.all(entries.map(async e => {
    const p = join(dir, e.name)
    try {
      const s = await stat(p)
      return { name: e.name, isDir: s.isDirectory(), size: s.size }
    } catch {
      return { name: e.name, isDir: e.isDirectory(), size: 0 }
    }
  }))
  return meta
}

router.get("/file-list", async (req, res) => {
  const { taskId } = req.query
  const dirPath = String(req.query.path || ".")
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  try {
    // Guarantee the standard dirs show up — only needed at the root listing.
    const atRoot = dirPath === "." || dirPath === "/" || dirPath === ""
    if (atRoot) await ensureTaskDirs(taskId, "input", "logs", "output")
    const { target, rel } = resolveTaskPath(taskId, dirPath)
    let items = []
    try {
      items = await listDir(target)
    } catch {
      await mkdir(target, { recursive: true })
      items = []
    }
    res.json({ path: rel || ".", items })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

router.get("/file-read", async (req, res) => {
  const { taskId, path: filePath } = req.query
  if (!taskId || !filePath) return res.status(400).json({ error: "taskId and path required" })
  try {
    const { target, rel } = resolveTaskPath(taskId, filePath)
    const content = await readFile(target, "utf8")
    res.json({ ok: true, content, path: rel })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

router.post("/file-write", async (req, res) => {
  const { taskId, path: filePath, content } = req.body
  if (!taskId || !filePath || content === undefined) return res.status(400).json({ error: "taskId, path, and content required" })
  try {
    const { target, rel } = resolveTaskPath(taskId, filePath)
    await mkdir(dirname(target), { recursive: true })
    await writeFile(target, String(content), "utf8")
    res.json({ ok: true, path: rel, bytes: Buffer.byteLength(String(content), "utf8") })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

router.post("/file-delete", async (req, res) => {
  const { taskId, path: filePath } = req.body
  if (!taskId || !filePath) return res.status(400).json({ error: "taskId and path required" })
  try {
    const { target } = resolveTaskPath(taskId, filePath)
    await rm(target, { force: true })
    res.json({ ok: true })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

router.post("/file-mkdir", async (req, res) => {
  const { taskId, path: dirPath } = req.body
  if (!taskId || !dirPath) return res.status(400).json({ error: "taskId and path required" })
  try {
    const { target } = resolveTaskPath(taskId, dirPath)
    await mkdir(target, { recursive: true })
    res.json({ ok: true })
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

export default router
