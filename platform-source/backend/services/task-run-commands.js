// Which steps the per-step Run buttons (start/stop/restart) can drive, and how
// long each command may take.
//
// The flow console advertises a Start/Stop/Restart control on every MD step
// (services/flow-overview.js buildControls), and each of those commands belongs
// to the step's own main.py. So a step is runnable exactly when it has one --
// the same condition routes/flows.js uses to decide whether to skip a step:
//
//   - local one-shot computations (magnetomech) run to completion in-process,
//     so there is no long-running process to start or stop;
//   - local generation steps (seq_to_pdb, tiger2_dcd_to_gromacs_cg_pdb) have no
//     main.py at all.
//
// Deciding here keeps the refusal a sentence a user can act on, instead of
// ENOENT or "unknown command" bubbling out of main.py.

export const RUN_COMMANDS = ["start", "stop", "restart"]

// start/restart launch (or relaunch) a remote run; stop only signals. The
// numbers match routes/flows.js (start) and tasks.js pause/continue (60 s).
export const RUN_COMMAND_TIMEOUT_MS = {
  start: 180_000,
  restart: 180_000,
  stop: 60_000,
}

// Returns a human explanation when `command` must be refused for `task`, or
// null when it should be delegated to the task's main.py. The caller supplies
// `hasMainPy` and `isLocal` so this stays pure and unit-testable.
export function runCommandRejection(task, command, { hasMainPy, isLocal }) {
  if (isLocal) {
    return `${task.taskType} runs to completion in this process, so it has no `
         + `${command}. Its Compute button runs it fresh.`
  }
  if (!hasMainPy) {
    return `${task.taskType} is a local generation step with no main.py, so it `
         + `cannot ${command}; use its Generate button.`
  }
  return null
}
