import { readFileSync } from "fs"
import { Client } from "ssh2"
import { serverStore } from "./store.js"

export const sshSessions = new Map()

export function getServerSession(serverId) {
  const session = sshSessions.get(serverId)
  if (!session || session.conn.closed) { sshSessions.delete(serverId); return null }
  return session
}

function buildConnectConfig(server) {
  const cfg = { host: server.host, port: server.port, username: server.username, readyTimeout: 10000 }
  if (server.password) cfg.password = server.password
  if (server.privateKey) {
    const keyPath = server.privateKey.replace(/^~(?=$|\/)/, process.env.HOME || process.env.USERPROFILE || "")
    try { cfg.privateKey = readFileSync(keyPath, "utf8") } catch (e) {
      console.error(`[SSH] Failed to read privateKey for "${server.name}": ${e.message}`)
    }
  }
  return cfg
}

export async function autoConnectServers() {
  for (const server of serverStore.servers) {
    if (!server.host || !server.username || (!server.password && !server.privateKey)) continue
    console.log(`[SSH] Auto-connecting "${server.name}" → ${server.username}@${server.host}...`)
    const conn = new Client()
    try {
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => { conn.end(); reject(new Error("timeout")) }, 10000)
        conn.on("ready", () => {
          clearTimeout(timer)
          sshSessions.set(server.id, { conn, host: server.host, username: server.username, port: server.port })
          console.log(`[SSH] Server "${server.name}" connected`)
          resolve()
        })
        conn.on("error", (err) => { clearTimeout(timer); reject(err) })
        conn.connect(buildConnectConfig(server))
      })
    } catch (e) {
      console.error(`[SSH] Server "${server.name}" auto-connect failed: ${e.message}`)
    }
  }
}
