// Flow templates: create a whole ordered, chained pipeline in one request.
//
// POST /api/flows/create only makes an empty flow, and the alternative -- adding
// tasks one at a time through POST /api/tasks/create and then hand-editing each
// one's `next` map -- makes the chaining rules something the user has to know
// and get right by hand. A template encodes them once, in the same place the
// steps are created, so the two cannot drift apart.
//
// Each template is a list of steps; a step's `outputs` are the files it produces
// that the next step consumes. Those are turned into the `next` wiring that
// POST /api/flows/:id/start already honours, so nothing new had to be invented
// for the data path -- this only removes the manual wiring.
import { Router } from "express"
import { flowStore, taskStore, saveFlows, saveTasks, isLocalTask, isTransitionTask } from "../store.js"
import { scaffoldTaskConfig, ensureTaskDirs } from "../services/task-dir.js"
import { syncFlowLinks } from "../services/flow-links.js"
import { syncFlowFolder } from "../services/flow-folder.js"
import { expireCache } from "../cache.js"

const router = Router()

// The chain the platform is built around: sequence -> TIGER2 (NAMD) ->
// coarse-grained GROMACS -> magnetomechanics. `needsServer` steps require an
// SSH target at creation time; the rest are local.
//
// Steps use the `flow_*` wrapper types, not the bare ones. The wrapper types are
// the ones with an editable Parameters panel (services/editable-params.js keys
// its specs on them), and they wrap the same underlying compute, so using the
// bare types here would produce a flow whose steps cannot be configured at all.
//
// TIGER2 -> CG used to be two steps with a `tiger2_dcd_to_gromacs_cg_pdb`
// conversion step in between. That step had no main.py, so flow start skipped
// it and it had to be triggered by hand. It is now folded into flow_tiger2,
// which produces the CG inputs from its own trajectory (see its main.py) -- so
// the chain is one compute step, then the CG step.
export const FLOW_TEMPLATES = {
  empty: {
    label: "Empty flow",
    description: "Just a flow. Add steps yourself.",
    steps: [],
  },
  tiger2: {
    label: "TIGER2 (NAMD) single step",
    description: "One all-atom simulation step.",
    steps: [
      { taskType: "flow_tiger2", name: "TIGER2", needsServer: true },
    ],
  },
  "tiger2-to-cg": {
    label: "TIGER2 → GROMACS CG",
    description: "All-atom simulation feeding a coarse-grained run.",
    steps: [
      // This step writes the CG start structure and .mdp itself: NAMD writes
      // DCD/coor/vel, which GROMACS cannot read, so the conversion is part of
      // the TIGER2 step rather than an optional extra — without it the CG step
      // has no topology and cannot be started.
      { taskType: "flow_tiger2", name: "TIGER2", needsServer: true },
      { taskType: "flow_gromacs_cg", name: "GROMACS CG", needsServer: true },
    ],
  },
  "full-chain": {
    label: "Full chain: TIGER2 → CG → Magnetomechanics",
    description:
      "All-atom, then coarse-grained, then the magnetomechanics analysis of the CG result.",
    steps: [
      { taskType: "flow_tiger2", name: "TIGER2", needsServer: true },
      { taskType: "flow_gromacs_cg", name: "GROMACS CG", needsServer: true },
      { taskType: "flow_magnetomech", name: "Magnetomechanics", needsServer: false },
    ],
  },
}

// Where each task type's produced files are handed to the next step.
//
// These names are read off what the steps actually write, not inferred:
//
//   flow_tiger2 writes output/cg_start.pdb, output/cg_input.mdp and
//     output/from-tiger2/ via the DCD -> CG conversion folded into it (see
//     tiger2_dcd_to_gromacs_cg_pdb/generate.py).
//   NAMD itself writes DCD/coor/vel/xsc and never a .pdb/.cif, so a handoff
//     naming those would copy nothing at all.
export const HANDOFF = {
  "flow_tiger2>flow_gromacs_cg": [
    { output: "cg_start.pdb", into: "input/cg_start.pdb" },
    { output: "cg_input.mdp", into: "input/cg_input.mdp" },
    { output: "from-tiger2", into: "input/from-tiger2" },
  ],
}

router.get("/templates", (_req, res) => {
  res.json({
    templates: Object.entries(FLOW_TEMPLATES).map(([id, t]) => ({
      id,
      label: t.label,
      description: t.description,
      steps: t.steps.map(s => ({ taskType: s.taskType, name: s.name })),
    })),
  })
})

// POST /api/flows/from-template -- create a flow plus its ordered steps.
router.post("/from-template", async (req, res) => {
  const { name, template = "empty", serverId = "" } = req.body
  if (!name || !String(name).trim()) return res.status(400).json({ error: "Flow name required" })
  const spec = FLOW_TEMPLATES[template]
  if (!spec) {
    return res.status(400).json({ error: `Unknown template "${template}". Available: ${Object.keys(FLOW_TEMPLATES).join(", ")}` })
  }

  // Every server-backed step needs a target, and it is checked before anything
  // is written so a failed create leaves no half-built flow behind.
  const needsServer = spec.steps.some(s => s.needsServer)
  if (needsServer && !serverId) {
    return res.status(400).json({
      error: `"${spec.label}" needs a server for its compute steps. Choose one and try again.`,
    })
  }

  const flow = {
    id: `flow_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
    name: String(name).trim(),
    createdAt: Date.now(),
  }
  const created = []

  try {
    flowStore.flows.push(flow)

    for (const step of spec.steps) {
      const id = `task_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
      // A local step runs in-process on this machine, so it keeps serverId ""
      // (see below). All compute steps in a template need a server.
      const local = isLocalTask({ taskType: step.taskType })
        || isTransitionTask({ taskType: step.taskType })
      const task = {
        id,
        name: step.name,
        // A local step keeps serverId "" so buildMainArgs never builds an SSH
        // hop for it, even if the flow was created against a server.
        serverId: local ? "" : serverId,
        workDir: "",
        scriptName: "",
        taskType: step.taskType,
        flowId: flow.id,
        createdAt: Date.now() + created.length,
      }
      taskStore.tasks.push(task)
      created.push(task)
      await ensureTaskDirs(id)
      await scaffoldTaskConfig(id, step.taskType, task.config || {})
    }

    // Wire each step's outputs into the next step's input. This is the same
    // `next` shape POST /api/tasks/create accepts, so flow start chains them
    // with no special-casing.
    for (let i = 0; i < created.length - 1; i++) {
      const from = created[i]
      const to = created[i + 1]
      const key = `${from.taskType}>${to.taskType}`
      const files = HANDOFF[key] || []
      if (files.length) from.next = [{ toTaskId: to.id, files }]
      // No explicit file map: magnetomech reads the CG summary through the
      // flow-scoped symlink that syncFlowLinks creates, which is why that step
      // chains without a `next` entry.
    }

    await saveFlows()
    await saveTasks()
    await syncFlowLinks()
    expireCache("tasks")
    syncFlowFolder(flow).catch(e => console.error("[FlowTemplates] folder sync:", e.message))

    res.json({ ok: true, flow, tasks: created.map(t => ({ id: t.id, name: t.name, taskType: t.taskType })) })
  } catch (e) {
    // Roll back so a partially-created pipeline does not linger: a flow with
    // one of three steps is worse than no flow, because it looks usable.
    for (const t of created) {
      const idx = taskStore.tasks.findIndex(x => x.id === t.id)
      if (idx !== -1) taskStore.tasks.splice(idx, 1)
    }
    const fi = flowStore.flows.findIndex(f => f.id === flow.id)
    if (fi !== -1) flowStore.flows.splice(fi, 1)
    await saveFlows().catch(() => {})
    await saveTasks().catch(() => {})
    res.status(500).json({ error: e.message })
  }
})

export default router