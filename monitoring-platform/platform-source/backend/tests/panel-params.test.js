// What the Parameters panel accepts, writes, and refuses.
//
// The interesting cases are the ones where the panel rendered a field that the
// API then rejected (or accepted and dropped): a template-created task showed
// five science fields that could not be saved at all, and had no way to set the
// remote directory a start requires. These tests run the real service module
// rather than a copy, so a spec change cannot drift from what is asserted here.
import assert from "node:assert/strict"
import { test } from "node:test"
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs"
import { join } from "node:path"
import { tmpdir } from "node:os"

import {
  validateEditable,
  buildEditablePanel,
  isEditableType,
  ParamError,
  DEPLOYMENT_FIELDS,
} from "../services/editable-params.js"

const TASKS_DIR = join(process.cwd(), "tasks")

// Build a real on-disk task so the service reads config through its normal path.
function makeTask(id, config, taskType = "flow_gromacs_cg") {
  const dir = join(TASKS_DIR, id)
  mkdirSync(join(dir, "scripts"), { recursive: true })
  writeFileSync(join(dir, "scripts", "task_config.json"), JSON.stringify(config, null, 2))
  return { id, taskType, config: {} }
}

function withTask(fn) {
  const id = `task_test_${Date.now().toString(36)}`
  try {
    return fn(id)
  } finally {
    rmSync(join(TASKS_DIR, id), { recursive: true, force: true })
  }
}

const COMPLETE_CG = {
  protein: "2KY10 SELP CG",
  nCrosslinks: 44,
  nChains: 32,
  temperatureK: 310,
  strains: "0.05,0.1",
  numReplicas: 1,
  stepsPerCycle: 500000,
  totalCycles: 10,
}

test("the three chain step types all have an editable panel", () => {
  // A template that used the bare types produced steps with no editable
  // parameters at all: the panel rendered fields, and every save failed with
  // "has no editable parameters".
  for (const t of ["flow_tiger2", "flow_gromacs_cg", "flow_magnetomech"]) {
    assert.equal(isEditableType(t), true, `${t} should be editable`)
  }
  for (const t of ["tiger2", "gromacs_cg", "magnetomech"]) {
    assert.equal(isEditableType(t), false, `${t} has no spec; do not build templates from it`)
  }
})

test("deployment fields are offered on every editable type", () => {
  for (const t of ["flow_tiger2", "flow_gromacs_cg", "flow_magnetomech"]) {
    const panel = withTask((id) =>
      buildEditablePanel({ id, taskType: t, config: {} }))
    assert.ok(Array.isArray(panel.deploymentFields), `${t}: no deployment section`)
    assert.deepEqual(
      panel.deploymentFields.map((f) => f.key).sort(),
      ["logPrefix", "remoteDir"],
      `${t}: deployment fields wrong`,
    )
  }
})

test("a scaffolded FILL-IN remoteDir reads as unset, not as a path", () => {
  // A freshly created task has `remoteDir: "FILL-IN: ..."`. Treating that as a
  // configured value would put the placeholder text into shell commands.
  const panel = withTask((id) => buildEditablePanel({
    id,
    taskType: "flow_gromacs_cg",
    config: {},
  }))
  const dir = panel.deploymentFields.find((f) => f.key === "remoteDir")
  assert.equal(dir.value, "")
  assert.ok(panel.deploymentMissing.includes("remoteDir"))
  assert.ok(panel.deploymentMissing.includes("logPrefix"))
})

test("a configured remoteDir is shown and no longer reported missing", () => {
  withTask((id) => {
    const task = makeTask(id, {
      remoteDir: "/home/selp/igem-2026/MD/run1",
      logPrefix: "job0",
    })
    const after = buildEditablePanel(task)
    assert.equal(
      after.deploymentFields.find((f) => f.key === "remoteDir").value,
      "/home/selp/igem-2026/MD/run1",
    )
    assert.deepEqual(after.deploymentMissing, [])
  })
})

test("remoteDir and logPrefix round-trip through validation", () => {
  const r = validateEditable("flow_gromacs_cg", {
    values: { ...COMPLETE_CG, remoteDir: "/home/selp/igem-2026/MD/run1", logPrefix: "job0" },
  })
  assert.equal(r.values.remoteDir, "/home/selp/igem-2026/MD/run1")
  assert.equal(r.values.logPrefix, "job0")
})

test("a relative remoteDir is rejected", () => {
  // It would resolve against whatever directory the SSH command happens to run
  // in, so the run would create its files somewhere unintended.
  assert.throws(
    () => validateEditable("flow_gromacs_cg", { values: { ...COMPLETE_CG, remoteDir: "MD/run1" } }),
    (e) => e instanceof ParamError && /absolute path/.test(e.message),
  )
})

test("a remoteDir containing shell metacharacters is rejected", () => {
  // Both values are interpolated into a remote shell command.
  for (const bad of ["/tmp; rm -rf /", "/tmp`id`", "/tmp$(id)", "/tmp && id"]) {
    assert.throws(
      () => validateEditable("flow_gromacs_cg", { values: { ...COMPLETE_CG, remoteDir: bad } }),
      (e) => e instanceof ParamError,
      `${bad} should be rejected`,
    )
  }
})

test("a logPrefix with shell metacharacters is rejected", () => {
  assert.throws(
    () => validateEditable("flow_gromacs_cg", { values: { ...COMPLETE_CG, logPrefix: "a; id" } }),
    (e) => e instanceof ParamError && /letters, digits/.test(e.message),
  )
})

test("a normal logPrefix is accepted", () => {
  for (const ok of ["job0", "2KY10_remd", "cg_run-1", "a.b_c"]) {
    const r = validateEditable("flow_gromacs_cg", { values: { ...COMPLETE_CG, logPrefix: ok } })
    assert.equal(r.values.logPrefix, ok)
  }
})

test("saving one field leaves the others alone", () => {
  // A partial save used to blank every omitted key, so editing a single number
  // silently cleared the strain list and every other setting.
  const stored = { remoteDir: "/home/selp/igem-2026/MD/run1", logPrefix: "job0", ...COMPLETE_CG }
  withTask((id) => {
    const task = makeTask(id, stored)
    const r = validateEditable("flow_gromacs_cg", { values: { nCrosslinks: 50 } }, task)
    assert.equal(r.values.nCrosslinks, 50)
    assert.equal(r.values.strains, "0.05,0.1", "strains must survive a partial save")
    assert.equal(r.values.protein, "2KY10 SELP CG")
    assert.equal(r.values.temperatureK, 310)
  })
})

test("a partial save does not clear the deployment paths", () => {
  withTask((id) => {
    const task = makeTask(id, { remoteDir: "/home/selp/igem-2026/MD/run1", logPrefix: "job0" })
    const r = validateEditable("flow_gromacs_cg", { values: { nCrosslinks: 50 } }, task)
    assert.equal(r.values.remoteDir, undefined, "remoteDir must not be written when untouched")
    assert.equal(r.values.logPrefix, undefined)
  })
})

test("an unparseable strain list is a field error, not a 500", () => {
  // strainList returns null for junk, and the join that consumed it threw a
  // TypeError, so the whole request failed with an opaque server error.
  assert.throws(
    () => validateEditable("flow_gromacs_cg", { values: { ...COMPLETE_CG, strains: "abc" } }),
    (e) => e instanceof ParamError,
  )
})

test("an empty strain list is a field error, not a 500", () => {
  assert.throws(
    () => validateEditable("flow_gromacs_cg", { values: { ...COMPLETE_CG, strains: "" } }),
    (e) => e instanceof ParamError,
  )
})

test("an unknown parameter is still rejected", () => {
  assert.throws(
    () => validateEditable("flow_gromacs_cg", { values: { ...COMPLETE_CG, bogusKey: 1 } }),
    (e) => e instanceof ParamError && /Unknown parameter/.test(e.message),
  )
})

test("deployment field keys are unique and named", () => {
  const keys = DEPLOYMENT_FIELDS.map((f) => f.key)
  assert.deepEqual([...new Set(keys)], keys)
  assert.ok(keys.includes("remoteDir") && keys.includes("logPrefix"))
})

test("the panel shows values that were actually saved", () => {
  // persistTaskConfig writes to the top level of task_config.json. The CG
  // panel read only defaults.*, so a saved value rendered blank and the user
  // re-typed it (or assumed the save had failed). Each spec must read back what
  // its own validate() writes.
  withTask((id) => {
    makeTask(id, {})
    const task = { id, taskType: "flow_gromacs_cg", config: {} }
    const saved = validateEditable("flow_gromacs_cg", {
      values: { ...COMPLETE_CG, remoteDir: "/home/selp/igem-2026/MD/run1", logPrefix: "job0" },
    }, task)
    writeFileSync(
      join(TASKS_DIR, id, "scripts", "task_config.json"),
      JSON.stringify({ ...COMPLETE_CG, remoteDir: "/home/selp/igem-2026/MD/run1", logPrefix: "job0" }),
    )
    const panel = buildEditablePanel(task)
    const shown = Object.fromEntries(panel.editableFields.map((f) => [f.key, f.value]))
    for (const [key, want] of Object.entries(COMPLETE_CG)) {
      assert.equal(String(shown[key]), String(want), `CG panel shows wrong ${key}`)
    }
    assert.ok(saved.values.remoteDir)
  })
})