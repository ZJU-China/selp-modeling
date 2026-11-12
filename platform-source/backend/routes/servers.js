import { readFileSync } from "fs"
import { Router } from "express"
import { Client } from "ssh2"
import { serverStore, saveServers } from "../store.js"
import { sshSessions, getServerSession } from "../ssh.js"

const router = Router()

router.get("/", (_req, res) => {
  res.json({ servers: serverStore.servers.map(s => ({ ...s, password: undefined, privateKey: undefined, connected: !!getServerSession(s.id) })) })
})

router.post("/create", async (req, res) => {
  const { name, host, port = 22, username, password, privateKey, startupCmd = "" } = req.body
  if (!name || !host || !username || (!password && !privateKey)) return res.status(400).json({ error: "name, host, username, and password or privateKey are required" })
  const id = `srv_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
  const server = { id, name, host, port: Number(port), username, password: password || "", privateKey: privateKey || "", startupCmd }
  serverStore.servers.push(server)
  await saveServers()
  res.json({ ok: true, server: { ...server, password: undefined, privateKey: undefined } })
})

router.put("/update", async (req, res) => {
  const { id, name, host, port, username, password, privateKey, startupCmd } = req.body
  if (!id) return res.status(400).json({ error: "id required" })
  const server = serverStore.servers.find(s => s.id === id)
  if (!server) return res.status(404).json({ error: "Server not found" })
  if (name !== undefined) server.name = name
  if (host !== undefined) server.host = host
  if (port !== undefined) server.port = Number(port)
  if (username !== undefined) server.username = username
  if (password !== undefined) server.password = password
  if (privateKey !== undefined) server.privateKey = privateKey
  if (startupCmd !== undefined) server.startupCmd = startupCmd
  await saveServers()
  res.json({ ok: true, server: { ...server, password: undefined, privateKey: undefined } })
})

router.delete("/delete", async (req, res) => {
  const { id } = req.body
  const idx = serverStore.servers.findIndex(s => s.id === id)
  if (idx === -1) return res.status(404).json({ error: "Server not found" })
  if (sshSessions.has(id)) { try { sshSessions.get(id).conn.end() } catch {}; sshSessions.delete(id) }
  serverStore.servers.splice(idx, 1)
  await saveServers()
  res.json({ ok: true })
})

router.post("/connect", async (req, res) => {
  const { id } = req.body
  const server = serverStore.servers.find(s => s.id === id)
  if (!server) return res.status(404).json({ error: "Server not found" })
  if (getServerSession(id)) { try { sshSessions.get(id).conn.end() } catch {}; sshSessions.delete(id) }
  const conn = new Client()
  let responded = false
  const timer = setTimeout(() => { if (responded) return; responded = true; try { conn.end() } catch {}; res.status(500).json({ error: "SSH connection timeout" }) }, 10000)
  conn.on("ready", () => {
    clearTimeout(timer); if (responded) return; responded = true
    sshSessions.set(id, { conn, host: server.host, username: server.username, port: server.port })
    res.json({ ok: true, message: `Connected to ${server.username}@${server.host}:${server.port}` })
  })
  conn.on("error", (err) => { clearTimeout(timer); if (responded) return; responded = true; res.status(500).json({ error: `SSH failed: ${err.message}` }) })
  const connectCfg = { host: server.host, port: server.port, username: server.username, readyTimeout: 10000 }
  if (server.password) connectCfg.password = server.password
  if (server.privateKey) {
    try { connectCfg.privateKey = readFileSync(server.privateKey, "utf8") } catch (e) {
      clearTimeout(timer); return res.status(500).json({ error: `Failed to read privateKey: ${e.message}` })
    }
  }
  conn.connect(connectCfg)
})

router.post("/disconnect", async (req, res) => {
  const { id } = req.body
  if (sshSessions.has(id)) { try { sshSessions.get(id).conn.end() } catch {}; sshSessions.delete(id) }
  res.json({ ok: true })
})

export default router
