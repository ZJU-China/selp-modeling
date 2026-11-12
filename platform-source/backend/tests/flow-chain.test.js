// Flow start must not run a downstream step against an incomplete input.
//
// The chain ran every task in creation order: it started TIGER2, moved on
// immediately, and then handed the transition step "source missing" for every
// file -- because TIGER2 was still running and had produced nothing yet. The
// response said ok:true, so the whole chain looked like it had worked while
// producing nothing.
//
// These tests pin the gating: a chain stops at a step that is still running and
// names it, rather than proceeding. They exercise the decision logic against
// recorded results, not a live cluster.
import assert from "node:assert/strict"
import { test } from "node:test"

// Mirror of the decision in routes/flows.js, kept here so the rule is stated
// once and tested. If the route changes, this is the place to look.
export function planChain(results, { dryRun = false, waitForCompletion = false } = {}) {
  let waiting = null
  for (const step of results) {
    const isTransition = step.transition === true
    if (isTransition) {
      // A transition that is still running after its wait window has a
      // half-written output.
      if (step.monitor?.finalRunning && !dryRun && !waitForCompletion) {
        waiting = {
          taskId: step.taskId,
          reason: "still running after its wait window, so its output is incomplete",
        }
        break
      }
      continue
    }
    const started = step.monitor?.started ?? false
    if (!started && step.start && !step.start.skipped) {
      return { ok: false, waiting: null, error: step.error || "task did not start" }
    }
    if (started && step.monitor?.running && !dryRun && !waitForCompletion) {
      waiting = {
        taskId: step.taskId,
        reason: "still running, so the next step has no input yet",
      }
      break
    }
  }
  const ok = !waiting && !results.some(s => s.error)
  return { ok, waiting }
}

const runningCompute = {
  taskId: "task_a",
  transition: false,
  start: { ok: true, running: true },
  monitor: { started: true, running: true },
}

test("a chain stops at a step that is still running", () => {
  const r = planChain([runningCompute])
  assert.equal(r.ok, false)
  assert.equal(r.waiting.taskId, "task_a")
  assert.match(r.waiting.reason, /no input yet/)
})

test("the waiting step is named so the user knows what to finish first", () => {
  const r = planChain([runningCompute])
  assert.ok(r.waiting.taskId, "the response must identify the blocking step")
})

test("a completed chain is ok", () => {
  const finished = {
    taskId: "task_a",
    transition: false,
    start: { ok: true, running: false },
    monitor: { started: true, running: false },
  }
  assert.equal(planChain([finished]).ok, true)
})

test("a step that failed to start is an error, not a wait", () => {
  // Distinguishing these matters: one needs the user to retry the start, the
  // other needs them to wait.
  const failed = {
    taskId: "task_a",
    transition: false,
    start: { ok: false, error: "No config dir" },
    monitor: { started: false, running: false },
    error: "task did not start",
  }
  const r = planChain([failed])
  assert.equal(r.waiting, null)
  assert.equal(r.ok, false)
  assert.match(r.error, /task did not start/)
})

test("a transition that is still running also stops the chain", () => {
  // Its output is half-written, so the successor would convert a truncated file.
  const busyTransition = {
    taskId: "task_x",
    transition: true,
    start: { ok: true },
    monitor: { waited: true, finalRunning: true },
  }
  const r = planChain([busyTransition])
  assert.equal(r.ok, false)
  assert.equal(r.waiting.taskId, "task_x")
})

test("a transition that finished does not block the chain", () => {
  const doneTransition = {
    taskId: "task_x",
    transition: true,
    start: { ok: true },
    monitor: { waited: true, finalRunning: false },
  }
  assert.equal(planChain([doneTransition]).ok, true)
})

test("a transition that failed is tolerated so the chain continues", () => {
  // Transitions can fail on missing upstream data; the successor's own start
  // reports that more usefully than the transition's failure does.
  const failedTransition = {
    taskId: "task_x",
    transition: true,
    start: { ok: false, error: "no input" },
    monitor: { waited: false },
  }
  assert.equal(planChain([failedTransition]).ok, true)
})

test("waitForCompletion overrides the gate", () => {
  // An explicit opt-in for callers that do want to block on a running step.
  const r = planChain([runningCompute], { waitForCompletion: true })
  assert.equal(r.waiting, null)
  assert.equal(r.ok, true)
})

test("dryRun never blocks on a running step", () => {
  const r = planChain([{ ...runningCompute, start: { dryRun: true } }], { dryRun: true })
  assert.equal(r.waiting, null)
})

test("a skipped local generation task does not fail the chain", () => {
  const skipped = {
    taskId: "task_s",
    transition: false,
    start: { ok: true, skipped: true, reason: "no main.py" },
    monitor: { skipped: true },
  }
  assert.equal(planChain([skipped]).ok, true)
})