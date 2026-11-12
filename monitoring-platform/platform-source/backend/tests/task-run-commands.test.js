// What the per-step Run buttons (start/stop/restart) accept and refuse.
//
// The flow console advertises Start/Stop/Restart on every MD step, but those
// controls pointed at routes that did not exist. The routes now delegate to the
// step's own main.py; what these tests pin is the gate in front of that call,
// against the real service module rather than a copy of its rule.
import assert from "node:assert/strict"
import { test } from "node:test"

import {
  RUN_COMMANDS,
  RUN_COMMAND_TIMEOUT_MS,
  runCommandRejection,
} from "../services/task-run-commands.js"

const mdStep = { taskType: "flow_tiger2" }
const localStep = { taskType: "magnetomech" }
const transitionStep = { taskType: "tiger2_dcd_to_gromacs_cg_pdb" }

test("a step with a main.py is runnable", () => {
  for (const command of RUN_COMMANDS) {
    assert.equal(
      runCommandRejection(mdStep, command, { hasMainPy: true, isLocal: false }),
      null,
      `${mdStep.taskType} ${command} should be allowed`,
    )
  }
})

test("a local one-shot computation is refused, not run to completion", () => {
  const reason = runCommandRejection(localStep, "start", { hasMainPy: true, isLocal: true })
  assert.ok(reason, "magnetomech must be refused")
  assert.match(reason, /Compute/)
  assert.match(reason, /magnetomech/)
})

test("a local generation step with no main.py is refused with a pointer to Generate", () => {
  const reason = runCommandRejection(transitionStep, "start", { hasMainPy: false, isLocal: false })
  assert.ok(reason, "a transition step must be refused")
  assert.match(reason, /Generate/)
  assert.match(reason, /main\.py/)
})

test("the refusal names the command the user pressed", () => {
  const reason = runCommandRejection(mdStep, "stop", { hasMainPy: false, isLocal: false })
  assert.match(reason, /stop/)
})

test("every advertised command has a timeout, and stop is the short one", () => {
  for (const command of RUN_COMMANDS) {
    assert.ok(
      Number.isFinite(RUN_COMMAND_TIMEOUT_MS[command]),
      `${command} needs a timeout`,
    )
  }
  assert.ok(RUN_COMMAND_TIMEOUT_MS.stop < RUN_COMMAND_TIMEOUT_MS.start)
  assert.ok(RUN_COMMAND_TIMEOUT_MS.stop < RUN_COMMAND_TIMEOUT_MS.restart)
})
