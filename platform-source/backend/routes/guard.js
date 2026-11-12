import { Router } from "express"
import { getGuardState, setTaskPaused, setGlobalPaused, appendEvent } from "../services/guard-state.js"
import { guardTask } from "../services/task-guard.js"
import { ping } from "../services/llm-client.js"

const router = Router()

// Current guard config + event history.
router.get("/status", async (_req, res) => {
  try {
    res.json(await getGuardState())
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// Toggle guard pause for one task.
router.post("/task/pause", async (req, res) => {
  const { taskId, paused } = req.body
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  try {
    await setTaskPaused(taskId, !!paused)
    res.json({ ok: true, taskId, paused: !!paused })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// Toggle guard pause globally.
router.post("/global/pause", async (req, res) => {
  const { paused } = req.body
  try {
    await setGlobalPaused(!!paused)
    res.json({ ok: true, paused: !!paused })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// Manually run the guard logic for one task (debug / force).
router.post("/check", async (req, res) => {
  const { taskId } = req.body
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  try {
    res.json(await guardTask(taskId))
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// LLM round-trip health check.
router.post("/test-llm", async (_req, res) => {
  try {
    res.json(await ping())
  } catch (e) { res.status(500).json({ error: e.message }) }
})

// Record a manual note/event (e.g. a human overrode a guard decision).
router.post("/note", async (req, res) => {
  const { taskId, message, level = "info" } = req.body
  if (!message) return res.status(400).json({ error: "message required" })
  try {
    const evt = await appendEvent({
      taskId: taskId || "(manual)", taskName: req.body.taskName || "", taskType: req.body.taskType || "",
      level, action: "note", source: "user", message,
    })
    res.json({ ok: true, event: evt })
  } catch (e) { res.status(500).json({ error: e.message }) }
})

export default router
