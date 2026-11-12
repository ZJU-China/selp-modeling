import test from "node:test"
import assert from "node:assert/strict"
import { validateEditable, checkFieldCsvHeader } from "../services/editable-params.js"

const DEFAULTS = {
  phiPolymer: "0.62",
  phiNanoparticle: "0.05",
  fieldMode: "uniform",
  maxT: "0.6",
  gradientDeltaT: "0.2",
  heightMm: "10",
  nPoints: "201",
}

function submit(over = {}, payload = {}) {
  return validateEditable("flow_magnetomech", {
    values: { ...DEFAULTS, ...over },
    annotations: [],
    ...payload,
  })
}

test("stores the two fractions as a composite block with water as the remainder", () => {
  const r = submit()
  assert.deepEqual(r.values.composite.species, {
    polymer: 0.62,
    nanoparticle: 0.05,
  })
  // Water is derived, never submitted, and the three must close on 1.
  assert.equal(r.values.composite.species.water, undefined)
  assert.ok(Math.abs(r.derived.phiWater - 0.33) < 1e-9)
  assert.ok(Math.abs(r.derived.phiTotal - 1) < 1e-9)
})

test("rejects fractions that leave negative water", () => {
  assert.throws(() => submit({ phiNanoparticle: "0.9" }), /must not exceed 1/)
})

test("the ion fraction is not an editable parameter", () => {
  // It had no mechanical effect, so exposing it only invited a knob that
  // changed nothing.
  assert.throws(() => submit({ phiIon: "0.2" }), /Unknown parameter "phiIon"/)
})

test("rejects a fraction above 1", () => {
  assert.throws(() => submit({ phiPolymer: "1.5" }), /1 \(100%\) or less/)
})

test("accepts fractions summing to exactly 1 with no water", () => {
  const r = submit({ phiPolymer: "0.95", phiNanoparticle: "0.05" })
  assert.ok(Math.abs(r.derived.phiWater - 0) < 1e-9)
})

test("empty fractions are read as zero rather than NaN", () => {
  const r = submit({ phiNanoparticle: "" })
  assert.equal(r.values.composite.species.nanoparticle, 0)
  assert.ok(Number.isFinite(r.derived.phiWater))
})

test("carries the field parameters through, defaulting an unknown mode to uniform", () => {
  const r = submit({ fieldMode: "csv" }, { files: { fieldFile: "input/p.csv" } })
  assert.equal(r.values.field.mode, "csv")
  assert.equal(r.values.field.csvPath, "input/p.csv")

  const bogus = submit({ fieldMode: "sideways" })
  assert.equal(bogus.values.field.mode, "uniform")
  assert.equal(bogus.values.field.csvPath, null)
})

test("csv mode without a file is refused, with the stage set for the form", () => {
  assert.throws(() => submit({ fieldMode: "csv" }), /no profile is uploaded/)
})

test("keeps an uploaded path when leaving csv mode, so switching back restores it", () => {
  // field.py only reads csvPath inside the csv branch (field.py:119-120), so a
  // retained path cannot affect a uniform/gradient run. Keeping it matches the
  // form, which also holds the attachment across a mode switch.
  const r = validateEditable("flow_magnetomech", {
    values: { ...DEFAULTS, fieldMode: "uniform" },
    annotations: [],
    files: { fieldFile: "input/left_behind.csv" },
  })
  assert.equal(r.values.field.mode, "uniform")
  assert.equal(r.values.field.csvPath, "input/left_behind.csv")
})

test("rejects an unknown parameter key", () => {
  assert.throws(() => submit({ demagFactor: "0.5" }), /Unknown parameter/)
})

test("profile point count must be a whole number of at least 2", () => {
  const r = submit({ nPoints: "51" })
  assert.equal(r.values.field.nPoints, 51)
  assert.throws(() => submit({ nPoints: "1.5" }), /whole number/i)
  assert.throws(() => submit({ nPoints: "1" }), /at least 2/i)
})

test("field header check accepts the columns field.py can read", () => {
  for (const header of ["z,B", "x,H", "z,h", "X, B"]) {
    const r = checkFieldCsvHeader(`${header}\n0,1\n1,0\n`)
    assert.ok(r.ok, `${header} should be accepted`)
  }
  // Mixed case is fine; field.py lowercases before matching.
  assert.ok(checkFieldCsvHeader("Z,B\n").ok)
})

test("field header check names the columns it found when they are unusable", () => {
  const noPos = checkFieldCsvHeader("depth,field\n0,1\n")
  assert.equal(noPos.ok, false)
  assert.match(noPos.error, /position column/)
  // The message lists what was there, so the user can see the mismatch.
  assert.match(noPos.error, /depth, field/)

  const noField = checkFieldCsvHeader("z,value\n0,1\n")
  assert.equal(noField.ok, false)
  assert.match(noField.error, /field column/)

  assert.equal(checkFieldCsvHeader("").ok, false)
  assert.match(checkFieldCsvHeader("").error, /empty/)
})

test("a csv with a header but no data rows is still a usable header", () => {
  // Only the header is validated at save time; the row count is the compute's
  // business, so this must not be rejected here.
  assert.ok(checkFieldCsvHeader("z,B\n").ok)
})

test("a millimetre column is accepted and labelled as such", () => {
  const r = checkFieldCsvHeader("z_mm,B\n0,0.1\n10,0.9\n", { heightMm: 10 })
  assert.ok(r.ok, r.error)
  assert.match(r.note, /\(mm\)/)
})

test("positions in millimetres under a bare z column are rejected", () => {
  // The panel collects height in mm, so this is the natural export -- but read
  // as metres it spans 0..10 m and only the origin row would count, leaving the
  // whole sample under a flat field.
  const r = checkFieldCsvHeader("z,B\n0,0.1\n5,0.35\n10,0.9\n", { heightMm: 10 })
  assert.equal(r.ok, false)
  assert.match(r.error, /z_mm/)
})

test("a profile that stops short of the sample is rejected", () => {
  const r = checkFieldCsvHeader("z,B\n0,0.1\n0.002,0.2\n", { heightMm: 10 })
  assert.equal(r.ok, false)
})

test("a millimetre profile under a bare z column is not rejected by magnitude alone", () => {
  // 10000x the height is what a mm-under-metres file looks like; a genuinely
  // huge sample would trip this too, so the check is deliberately loose.
  const r = checkFieldCsvHeader("z,B\n0,0.1\n0.01,0.9\n", { heightMm: 10 })
  assert.ok(r.ok, r.error)
})
