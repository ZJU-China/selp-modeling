import { Router } from "express"
import { createReadStream } from "fs"
import { stat } from "fs/promises"
import { startVideoRender, getVideoStatus, getVideoFile, isVideoFresh } from "../services/trajectory-video.js"

const router = Router()

const parseFull = v => v === "1" || v === "true"
const parseFormat = v => (v === "gif" ? "gif" : "mp4")

// Start rendering of the trajectory animation for a replica as an MP4
// (default) or GIF. Every call re-renders from scratch — the cached file is
// deleted first, so downloads always reflect the current renderer. Returns
// immediately; poll /status while it renders. Pass full=1 to render the entire
// trajectory instead of the tail window.
router.post("/render", async (req, res) => {
  const { taskId, replica = 0 } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  try {
    res.json(await startVideoRender(taskId, Number(replica), { full: parseFull(req.query.full), format: parseFormat(req.query.format) }))
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

router.get("/status", async (req, res) => {
  const { taskId, replica = 0 } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  try {
    res.json(await getVideoStatus(taskId, Number(replica), parseFull(req.query.full), parseFormat(req.query.format)))
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

// Stream the rendered MP4/GIF as a downloadable attachment. If the cached
// render was produced with older code/settings it is re-rendered first (202
// with the poll endpoint), so downloads always reflect the current renderer.
router.get("/download", async (req, res) => {
  const { taskId, replica = 0 } = req.query
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  try {
    const full = parseFull(req.query.full)
    const format = parseFormat(req.query.format)
    if (!(await isVideoFresh(taskId, Number(replica), full, format))) {
      await startVideoRender(taskId, Number(replica), { full, format })
      return res.status(202).json({ status: "rendering", message: "Re-rendering with current settings" })
    }
    const file = await getVideoFile(taskId, Number(replica), full, format)
    if (!file) return res.status(404).json({ error: "Video not rendered yet" })
    const info = await stat(file)
    res.setHeader("Content-Type", format === "gif" ? "image/gif" : "video/mp4")
    res.setHeader("Content-Length", info.size)
    res.setHeader("Content-Disposition", `attachment; filename="${taskId}_rep${replica}${full ? "_full" : ""}.${format === "gif" ? "gif" : "mp4"}"`)
    createReadStream(file).pipe(res)
  } catch (e) {
    res.status(500).json({ error: e.message })
  }
})

export default router
