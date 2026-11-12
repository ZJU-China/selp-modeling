// What a task will actually run against, for the Flow Console.
//
// The panel used to show nothing about the execution environment, so "which
// server does this task use" and "where do its files live" could only be
// answered by reading tasks.json. Worse, a stale tool path (gmx, matlab)
// surfaced only as a failed run.
//
// Tool resolution is NOT reimplemented here: _shared/tools.py is the single
// source of truth, and this shells out to it. Duplicating the lookup rules in
// JS is exactly the drift that made the gmx default wrong in the first place.
//
// Credentials are deliberately never returned. A server without a private key
// authenticates with a password, and that password must not reach the browser
// or any API response.
import { execFile } from "child_process"
import { existsSync } from "fs"
import { join } from "path"
import { serverStore, isLocalTask } from "../store.js"
import { getTaskBaseDir, getTaskConfigPath, getTaskInputDir, getTaskOutputDir } from "./task-dir.js"
import { getTaskTypeDir } from "./task-dir.js"

const TOOL_TIMEOUT_MS = 15000

// Ask the Python resolver how these tools resolve *here* -- the backend runs on
// the same host that runs the tasks, so its PATH is the deployment's PATH.
function resolveTools(taskId) {
  const python = join(getTaskTypeDir(), "_shared", "tools_probe.py")
  if (!existsSync(python)) return null
  return new Promise(resolve => {
    const args = [python, getTaskConfigPath(taskId)]
    execFile("python3", args, { timeout: TOOL_TIMEOUT_MS }, (err, stdout) => {
      if (err) {
        return resolve({ error: err.stderr?.slice(0, 500) || err.message })
      }
      try {
        resolve(JSON.parse(stdout))
      } catch (e) {
        resolve({ error: `tool probe returned unparseable output: ${e.message}` })
      }
    })
  })
}

export async function buildExecution(task) {
  const local = isLocalTask(task)
  const server = serverStore.servers.find(s => s.id === task.serverId) || null

  const connection = local
    ? {
        mode: "local",
        label: "Runs on this machine (no SSH)",
        host: null,
        port: null,
        username: null,
        // Local tasks still inherit the server's NAMD path when one is set,
        // because "local" here means no SSH hop, not "no remote-style tools".
        namdBin: server?.namdBin || null,
      }
    : server
      ? {
          mode: "ssh",
          label: `SSH to ${server.username}@${server.host}:${server.port || 22}`,
          host: server.host,
          port: server.port || 22,
          username: server.username,
          namdBin: server.namdBin || null,
        }
      : {
          // Not a local task type and no server resolved: run-main.js will throw
          // "Server not found". Say so here instead of implying it will work.
          mode: "unresolved",
          label: "No server configured for this task",
          host: null,
          port: null,
          username: null,
          namdBin: null,
        }

  return {
    connection,
    paths: {
      base: getTaskBaseDir(task.id),
      input: getTaskInputDir(task.id),
      output: getTaskOutputDir(task.id),
      // Where the remote side works; only meaningful for ssh tasks.
      remoteWorkDir: task.workDir || null,
    },
    tools: await resolveTools(task.id),
  }
}