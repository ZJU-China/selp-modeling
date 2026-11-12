// Transition-task generator runner. Transition task types (seq_to_pdb,
  // tiger2_dcd_to_gromacs_cg_pdb) produce local files (PDB / CSV / config templates) inside the
// task's own backend/tasks/<id> tree. They never SSH into a remote host, so
// unlike runMain they invoke the tasktype's generate.py directly with python3.
import { execFile } from "child_process"
import { existsSync } from "fs"
import { join } from "path"
import { taskStore } from "../store.js"
import { getTaskBaseDir, getTaskConfigPath, getTaskTypeDir, persistTaskConfig } from "./task-dir.js"

export async function runTransition(taskId, opts = {}) {
  const task = taskStore.tasks.find(t => t.id === taskId)
  if (!task) return Promise.reject(new Error("Task not found"))

  const script = join(getTaskTypeDir(), task.taskType, "generate.py")
  if (!existsSync(script)) {
    return Promise.reject(new Error(`No generator (generate.py) for task type "${task.taskType}"`))
  }

  // For transition tasks the form data lives in the store config
  // (PUT /api/tasks/update), which is authoritative. Write it back into the
  // task's scripts/task_config.json (merging over any scaffold defaults) so
  // generate.py always sees the current form values. persistTaskConfig merges
  // deeply, so a partial config never drops a nested scaffold section.
  const cfgPath = getTaskConfigPath(taskId)
  await persistTaskConfig(taskId, task.config)

  const args = [script, "--task-id", taskId, "--local-dir", getTaskBaseDir(taskId)]
  if (existsSync(cfgPath)) args.push("--task-config", cfgPath)

  return new Promise((resolve, reject) => {
    execFile("python3", args, {
      timeout: opts.timeout ?? 120000,
      maxBuffer: opts.maxBuffer ?? 10 * 1024 * 1024,
    }, (err, stdout, stderr) => {
      if (err) return reject(new Error(stderr?.slice(0, 2000) || err.message))
      try { resolve(JSON.parse(stdout)) }
      catch { resolve({ raw: stdout.trim() }) }
    })
  })
}
