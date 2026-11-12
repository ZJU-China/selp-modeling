import { readFile, writeFile } from "fs/promises"
import { existsSync } from "fs"
import { join } from "path"
import { getTaskCacheDir } from "./task-dir.js"

const STATE_FILE = "_convergence_state.json"

async function readState(taskId) {
  const path = join(getTaskCacheDir(taskId), STATE_FILE)
  try {
    if (existsSync(path)) return JSON.parse(await readFile(path, "utf8"))
  } catch {}
  return {}
}

export async function setConvergenceStopped(taskId, stopped) {
  const path = join(getTaskCacheDir(taskId), STATE_FILE)
  const state = await readState(taskId)
  state[taskId] = { ...(state[taskId] || {}), stopped: !!stopped }
  await writeFile(path, JSON.stringify(state, null, 2))
}
