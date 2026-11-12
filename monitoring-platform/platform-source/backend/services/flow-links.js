// Flow chaining: within a flow, each task's input directory links to the
// previous task's output directory, so downstream tasks can read what the
// upstream task produced (e.g. a tiger2_dcd_to_gromacs_cg_pdb transition task consuming the
// tiger2 task's output, or a GROMACS CG task consuming the transition task's
// generated inputs).
//
// Links are implemented as a single relative symlink per task:
//
//     backend/tasks/<taskId>/input/flow-<prevTaskId> -> ../../<prevTaskId>/output
//
// The symlink lives inside the task's own input dir (never escaping the task
// base dir lexically), so the file browser's resolveTaskPath stays safe while
// readdir/stat follow it transparently. syncFlowLinks() is called whenever the
// task/flow structure changes (task created, task moved between flows, task
// deleted, flow deleted) and is idempotent.
import { readdir, mkdir, unlink, symlink } from "fs/promises"
import { existsSync, lstatSync } from "fs"
import { join } from "path"
import { taskStore, flowStore } from "../store.js"
import { getTaskInputDir, getTaskBaseDir } from "./task-dir.js"

const LINK_PREFIX = "flow-"

export function flowLinkName(prevTaskId) {
  return `${LINK_PREFIX}${prevTaskId}`
}

// Tasks of a flow in pipeline order (creation order).
export function flowOrderFor(flowId) {
  return taskStore.tasks
    .filter(t => t.flowId === flowId)
    .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0) || 0)
}

function isSymlink(p) {
  try { return lstatSync(p).isSymbolicLink() } catch { return false }
}

async function applyLink(taskId, prevTaskId) {
  const inputDir = getTaskInputDir(taskId)
  await mkdir(inputDir, { recursive: true })

  let entries = []
  try { entries = await readdir(inputDir) } catch {}
  for (const e of entries) {
    if (e.startsWith(LINK_PREFIX)) {
      const p = join(inputDir, e)
      if (isSymlink(p)) {
        try { await unlink(p) } catch {}
      }
    }
  }

  if (!prevTaskId) return
  // Make sure the predecessor's output dir exists so the link is a valid,
  // navigable directory even before the upstream task has generated anything.
  try { await mkdir(join(getTaskBaseDir(prevTaskId), "output"), { recursive: true }) } catch {}
  const linkPath = join(inputDir, flowLinkName(prevTaskId))
  if (existsSync(linkPath)) {
    try { await unlink(linkPath) } catch {}
  }
  // Relative target: from <taskId>/input up two levels to the tasks root,
  // then into <prevTaskId>/output.
  try {
    await symlink(join("..", "..", prevTaskId, "output"), linkPath, "dir")
  } catch (e) {
    if (e.code !== "EEXIST") console.warn(`[FlowLinks] link ${linkPath}: ${e.message}`)
  }
}

// Rebuild every task's flow link. Safe to call unconditionally; each task's
// input keeps exactly one flow-<prevId> symlink matching its predecessor.
//
// A task may pin its upstream producer explicitly via task.upstreamTaskId,
// which is what keeps the link correct when a flow's *displayed* step list is
// not the same as its data lineage. The CG step consumes the transition task's
// converted cg_start.pdb, not the raw all-atom output of the step before it in
// the UI, so hiding the transition step must not silently rewire the CG step to
// point at the wrong directory.
export async function syncFlowLinks() {
  const ordered = new Map()
  for (const flow of flowStore.flows) {
    ordered.set(flow.id, flowOrderFor(flow.id))
  }
  const known = new Set(taskStore.tasks.map(t => t.id))
  for (const task of taskStore.tasks) {
    const seq = ordered.get(task.flowId) || []
    const idx = seq.findIndex(t => t.id === task.id)

    let prev = idx > 0 ? seq[idx - 1].id : null
    // A pinned upstream wins, but only when it still exists and is not the
    // task itself; otherwise fall back to positional chaining.
    if (task.upstreamTaskId && known.has(task.upstreamTaskId) && task.upstreamTaskId !== task.id) {
      prev = task.upstreamTaskId
    }
    await applyLink(task.id, prev)
  }
}
