import { Router } from "express"
import { taskStore } from "../store.js"
import { runTransition } from "../services/transition.js"
import { invalidateCache } from "../cache.js"

const router = Router()

router.post("/generate", async (req, res) => {
  const { taskId } = req.body
  if (!taskId) return res.status(400).json({ error: "taskId required" })
  const task = taskStore.tasks.find(t => t.id === taskId)
  if (!task) return res.status(404).json({ error: "Task not found" })
  try {
    const result = await runTransition(taskId)
    invalidateCache(taskId)
    res.json(result)
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message })
  }
})

export default router
