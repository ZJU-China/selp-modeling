import express from "express"
import { join, dirname } from "path"
import { fileURLToPath } from "url"
import { initStore } from "./store.js"
import { autoConnectServers } from "./ssh.js"
import { startSync } from "./sync.js"
import { syncFlowLinks } from "./services/flow-links.js"
import serverRoutes from "./routes/servers.js"
import taskRoutes from "./routes/tasks.js"
import taskFigureRoutes from "./routes/task-figures.js"
import fileRoutes from "./routes/files.js"
import dataRoutes from "./routes/data.js"
import videoRoutes from "./routes/video.js"
import flowRoutes from "./routes/flows.js"
import flowPageRoutes from "./routes/flow-pages.js"
import flowTemplateRoutes from "./routes/flow-templates.js"
import transitionRoutes from "./routes/transition.js"
import guardRoutes from "./routes/guard.js"
import chatRoutes from "./routes/chat.js"
import { startGuard } from "./services/task-guard.js"

process.on("uncaughtException", (err) => {
  console.error("[FATAL] Uncaught exception:", err.stack || err)
})
process.on("unhandledRejection", (reason) => {
  console.error("[FATAL] Unhandled rejection:", reason)
})

await initStore()

const app = express()
app.use(express.json())
app.use(express.raw({ type: "application/octet-stream", limit: "50mb" }))

app.use("/api/servers", serverRoutes)
app.use("/api/tasks", taskRoutes)
app.use("/api/tasks", taskFigureRoutes)
app.use("/api/tasks", fileRoutes)
app.use("/api/data", dataRoutes)
app.use("/api/video", videoRoutes)
app.use("/api/flows", flowRoutes)
// Flow-centric read model (overview / pages / per-task detail / folder sync).
// Mounted on the same prefix after flowRoutes: its paths (/pages, /:id/overview,
// /folders*) do not overlap flowRoutes' (/, /create, /rename, /delete,
// /:id/start, /:id/append-magnetomech), so Express falls through cleanly.
app.use("/api/flows", flowTemplateRoutes)
app.use("/api/flows", flowPageRoutes)
app.use("/api/transition", transitionRoutes)
app.use("/api/guard", guardRoutes)
app.use("/api/chat", chatRoutes)

autoConnectServers().catch(() => {})
startSync()
syncFlowLinks().catch(() => {})

// AI task guard: watches for unexpected failures and auto-recovers.
// Disable with MD_GUARD=off. Interval in ms via MD_GUARD_INTERVAL.
if (process.env.MD_GUARD !== "off") {
  const interval = Number(process.env.MD_GUARD_INTERVAL) || 60000
  startGuard(interval)
}

const PORT = process.env.API_PORT || 3001
app.listen(PORT, "0.0.0.0", () => {
  console.log(`[MD API] Backend running on http://0.0.0.0:${PORT}`)
})
