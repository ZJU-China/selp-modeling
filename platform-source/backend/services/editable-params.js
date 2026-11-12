// Editable Parameters panels.
//
// A task type becomes editable by adding one entry to SPECS. Each spec owns
// three things together on purpose:
//   fields      what the form renders
//   read        where the current values live
//   validate    what a submission may contain
// Keeping them in one object is what stops the rendered form and the endpoint
// that backs it from drifting apart -- a field added to one and not the other
// used to be a silent no-op.
//
// This is the general form of the "Parameters column is a fillable page" rule.
// A read-only panel is the default; a type opts in here.
import { readFileSync } from "fs"
import { join } from "path"
import { getTaskBaseDir } from "./task-dir.js"

const STANDARD_AA = "ACDEFGHIKLMNPQRSTVWY"
const HEX_COLOR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/

// The deformation sweep the generated CG driver enumerates (STRAINS in its
// driver script).
const DEFAULT_STRAINS = [0.05, 0.1]

// Thrown for anything the user can fix; the route turns this into a 400.
export class ParamError extends Error {
  constructor(message, stage) {
    super(message)
    this.stage = stage || null
  }
}

// Sequence input is typed as one long string; drop whitespace and punctuation
// and uppercase, which is how the coordinate builder expects it.
function normaliseSequence(raw) {
  return String(raw || "").replace(/[^A-Za-z]/g, "").toUpperCase()
}

function unsupportedLetters(seq) {
  return [...new Set(seq.split("").filter(c => !STANDARD_AA.includes(c)))]
}

export function csvCell(v) {
  const s = String(v ?? "")
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function annotationsCsv(rows) {
  return "sequence,label,color\n"
    + rows.map(r => [r.sequence, r.label, r.color].map(csvCell).join(",")).join("\n")
    + (rows.length ? "\n" : "")
}

function readTaskConfig(taskId) {
  try {
    return JSON.parse(readFileSync(join(getTaskBaseDir(taskId), "scripts", "task_config.json"), "utf8"))
  } catch {
    return {}
  }
}

function num(value, { key, min = null, step = null, integer = false }) {
  const raw = String(value ?? "").trim()
  if (raw === "") return null
  const n = Number(raw)
  if (!Number.isFinite(n)) throw new ParamError(`${key} must be a number`, key)
  if (integer && !Number.isInteger(n)) throw new ParamError(`${key} must be a whole number`, key)
  if (min !== null && n < min) throw new ParamError(`${key} must be at least ${min}`, key)
  if (step !== null && step >= 1 && n % step !== 0) {
    throw new ParamError(`${key} must be a multiple of ${step}`, key)
  }
  return n
}

function str(value) {
  return String(value ?? "").trim()
}

// A volume fraction: finite, within [0, 1].
function fraction(value, key) {
  const n = num(value, { key, min: 0 })
  if (n === null) return 0
  if (n > 1) throw new ParamError(`${key} must be 1 (100%) or less`, key)
  return n
}

// field.py looks CSV header columns up case-insensitively by exact name, so the
// uploaded-file validation has to agree with it exactly. The _mm/_m variants are
// the ones that matter in practice: the panel collects height in millimetres, so
// a profile exported in mm read as metres is 1000x too large and clamps to a
// flat field instead of failing.
const POSITION_COLUMNS = ["z", "x"]
const FIELD_COLUMNS = ["b", "h"]
const MM_POSITION_COLUMNS = ["z_mm", "x_mm", "position_mm"]

// A list-valued field is stored as a normalised string ("0.05,0.1") because that
// is what a single <input> submits, but older configs and hand-written
// task_config.json hold a real array. Both have to read back the same way.
function listToText(value) {
  if (Array.isArray(value)) return value.join(",")
  return String(value ?? "")
}

// "0.05, 0.10" -> [0.05, 0.1]
function strainList(value) {
  const raw = String(value ?? "").trim()
  if (!raw) return null
  const parts = raw.split(",").map(s => s.trim()).filter(Boolean)
  const out = []
  for (const p of parts) {
    const n = Number(p)
    if (!Number.isFinite(n)) throw new ParamError(`Stretch: "${p}" is not a number`, "strains")
    if (n <= 0) throw new ParamError("Stretch strains must be greater than 0", "strains")
    if (n > 1) throw new ParamError("Stretch strains must be 1 (100%) or less", "strains")
    out.push(n)
  }
  if (!out.length) return null
  return out
}

// ---------------------------------------------------------------------------
// Specs
// ---------------------------------------------------------------------------

const SPECS = {
  // sequence -> extended PDB -> TIGER2, as one task
  flow_tiger2: {
    title: "Sequence & annotation input",
    fields: [
      { key: "protein", label: "Protein", type: "text", placeholder: "e.g. 2KY10 SELP (339 aa)" },
      {
        key: "sequence",
        label: "Amino-acid sequence",
        type: "sequence",
        placeholder: "ACDEFGHIKL...",
        hint: "One-letter codes. The extended structure is rebuilt from this on every start.",
      },
      {
        key: "psf",
        label: "PSF topology",
        type: "text",
        placeholder: "protein.psf",
        hint: "Built by psfgen on the remote host and placed in this task's input/. Required before NAMD can start.",
      },
    ],
    annotations: true,
    read(task) {
      const cfg = { ...readTaskConfig(task.id), ...(task.config || {}) }
      return {
        values: {
          protein: cfg.protein || cfg.defaults?.protein || "",
          sequence: cfg.sequence || "",
          psf: cfg.psf || "",
        },
        annotations: Array.isArray(cfg.annotations) ? cfg.annotations : [],
      }
    },
    validate(values, annotations) {
      const sequence = normaliseSequence(values.sequence)
      if (!sequence) throw new ParamError("Sequence is required", "sequence")
      const bad = unsupportedLetters(sequence)
      if (bad.length) {
        throw new ParamError(`Unsupported amino-acid code(s): ${bad.join(", ")}`, "sequence")
      }
      const psf = str(values.psf)
      if (psf.includes("..")) {
        throw new ParamError("PSF filename must not contain '..'", "psf")
      }
      const rows = []
      for (const [i, r] of (Array.isArray(annotations) ? annotations : []).entries()) {
        const motif = normaliseSequence(r?.sequence)
        if (!motif) continue
        const badMotif = unsupportedLetters(motif)
        if (badMotif.length) {
          throw new ParamError(`Annotation ${i + 1}: unsupported amino-acid code(s): ${badMotif.join(", ")}`, "annotations")
        }
        // Motifs are matched as contiguous substrings of the sequence (see
        // _shared/sequence_annotation.py). One that never occurs highlights
        // nothing and reads as a broken viewer, so reject it rather than
        // silently accepting a table that cannot colour anything.
        if (!sequence.includes(motif)) {
          throw new ParamError(`Annotation ${i + 1} ("${motif}") does not occur in the sequence`, "annotations")
        }
        const color = str(r?.color)
        if (color && !HEX_COLOR.test(color)) {
          throw new ParamError(`Annotation ${i + 1}: "${color}" is not a hex colour`, "annotations")
        }
        rows.push({ sequence: motif, label: str(r?.label) || motif, color })
      }
      return {
        values: { protein: str(values.protein), sequence, psf },
        annotations: rows,
      }
    },
  },

  // magnetomech composite: polymer and nanoparticle fractions plus the
  // applied field. Water is whatever is left over.
  flow_magnetomech: {
    title: "Polymer & nanoparticle fractions, applied field",
    fields: [
      {
        key: "phiPolymer",
        label: "Polymer fraction",
        type: "number",
        step: 0.001,
        min: 0,
        max: 1,
        placeholder: "0.62",
        partOfSum: true,
        hint: "Volume fraction of the crosslinked polymer skeleton. The CG network modulus is a unit-concentration property, so this scales the loaded-sample stiffness.",
      },
      {
        key: "phiNanoparticle",
        label: "Nanoparticle fraction",
        type: "number",
        step: 0.001,
        min: 0,
        max: 1,
        placeholder: "0.05",
        partOfSum: true,
        hint: "The only magnetic phase: drives magnetization, the internal field and the dipole energy density.",
      },
      {
        key: "fieldMode",
        label: "Field mode",
        type: "select",
        options: [
          { value: "uniform", label: "Uniform" },
          { value: "gradient", label: "Gradient" },
          { value: "csv", label: "From file" },
        ],
        hint: "Uniform and gradient generate the profile; From file uses an uploaded CSV (position column z or x, field column b or h).",
      },
      {
        key: "maxT",
        label: "Base field",
        type: "number",
        step: 0.01,
        min: 0,
        unit: "T",
        placeholder: "0.6",
        when: { fieldMode: ["uniform", "gradient"] },
        hint: "The field at the starting end of the sample. In Gradient mode the field rises from here, so the peak is this value plus the field rise.",
      },
      {
        key: "gradientDeltaT",
        label: "Field rise",
        type: "number",
        step: 0.01,
        unit: "T",
        placeholder: "0.2",
        when: { fieldMode: ["gradient"] },
        hint: "How much the field rises across the sample height, from the peak field at one end.",
      },
      {
        key: "heightMm",
        label: "Sample height",
        type: "number",
        step: 0.1,
        min: 0,
        unit: "mm",
        placeholder: "10",
      },
      {
        key: "nPoints",
        label: "Profile points",
        type: "number",
        step: 1,
        min: 2,
        placeholder: "201",
        hint: "Samples along the sample height.",
      },
    ],
    annotations: false,
    // magnetomech is a one-shot local compute, so there is no run to restart.
    // "Compute" is the run action and it re-synthesizes from the panel every
    // time, so offering "Save & restart" would only report "not applicable".
    restart: false,
    // The uploaded profile lives as a file in input/, not in task_config.json,
    // so the form renders a file slot for it and the endpoint validates the
    // header rather than the value.
    fileField: {
      key: "fieldFile",
      label: "Field profile CSV",
      accept: ".csv,text/csv",
      dir: "input",
      when: { fieldMode: ["csv"] },
      columns: { position: POSITION_COLUMNS, field: FIELD_COLUMNS },
    },
    read(task) {
      const cfg = readTaskConfig(task.id)
      const comp = (cfg.composite && cfg.composite.species) || {}
      const fieldCfg = cfg.field || {}
      const phi = name => (comp[name] && comp[name].phi) ?? null
      return {
        values: {
          phiPolymer: phi("polymer") ?? 0.62,
          phiNanoparticle: phi("nanoparticle") ?? (cfg.particle || {}).phi ?? 0.05,
          fieldMode: fieldCfg.mode || "uniform",
          maxT: fieldCfg.maxT ?? 0.6,
          gradientDeltaT: fieldCfg.gradientDeltaT ?? 0.2,
          heightMm: fieldCfg.heightMm ?? 10,
          nPoints: fieldCfg.nPoints ?? 201,
        },
        annotations: [],
        files: { fieldFile: fieldCfg.csvPath || null },
      }
    },
    validate(values, _annotations, payload = {}) {
      const phis = {
        polymer: fraction(values.phiPolymer, "Polymer fraction"),
        nanoparticle: fraction(values.phiNanoparticle, "Nanoparticle fraction"),
      }
      const used = phis.polymer + phis.nanoparticle
      if (used > 1 + 1e-9) {
        throw new ParamError(
          `The two fractions add up to ${used.toFixed(4)}, which leaves ${(1 - used).toFixed(4)} for water. Their sum must not exceed 1.`,
          "phiNanoparticle",
        )
      }
      const fieldMode = ["uniform", "gradient", "csv"].includes(values.fieldMode)
        ? values.fieldMode
        : "uniform"
      const fieldFile = str(payload.files?.fieldFile)
      if (fieldMode === "csv" && !fieldFile) {
        throw new ParamError(
          "Field mode is \"From file\" but no profile is uploaded. Upload a CSV, or switch back to Uniform.",
          "fieldFile",
        )
      }
      return {
        values: {
          composite: { species: phis },
          field: {
            mode: fieldMode,
            maxT: num(values.maxT, { key: "Peak field", min: 0 }) ?? 0.6,
            gradientDeltaT: num(values.gradientDeltaT, { key: "Field drop", min: 0 }) ?? 0.2,
            heightMm: num(values.heightMm, { key: "Sample height", min: 0 }) ?? 10,
            nPoints: num(values.nPoints, { key: "Profile points", min: 2, step: 1, integer: true }) ?? 201,
            csvPath: fieldFile || null,
          },
        },
        annotations: [],
        derived: { phiWater: 1 - used, phiTotal: used + (1 - used) },
      }
    },
  },

  // CG network + uniaxial deformation windows, as one task
  flow_gromacs_cg: {
    title: "CG network & deformation input",
    fields: [
      { key: "protein", label: "System", type: "text", placeholder: "2KY10 SELP CG network" },
      {
        key: "nCrosslinks",
        label: "Crosslinks",
        type: "number",
        step: 1,
        min: 0,
        placeholder: "44",
        ratioOf: ["nCrosslinks", "nChains"],
        ratioLabel: "crosslinks per chain",
        hint: "Crosslink edges in the periodic CG network (expected-pairs when the topology is prepared).",
      },
      {
        key: "nChains",
        label: "Chains",
        type: "number",
        step: 1,
        min: 1,
        placeholder: "32",
        hint: "Chains in the periodic CG network.",
      },
      {
        key: "temperatureK",
        label: "Temperature",
        type: "number",
        step: 0.1,
        unit: "K",
        placeholder: "310",
        hint: "Thermostat written into the GROMACS mdp as ref-t.",
      },
      {
        key: "strains",
        label: "Stretch",
        type: "list",
        number: true,
        placeholder: "0.05,0.10",
        unit: "ε",
        hint: "Axial Hencky strains sampled along each axis by the uniaxial deformation windows.",
      },
      { key: "numReplicas", label: "Replicas", type: "number", step: 1, min: 1, placeholder: "1" },
      { key: "stepsPerCycle", label: "Steps / cycle", type: "number", step: 1, min: 1, placeholder: "500000" },
      { key: "totalCycles", label: "Cycles", type: "number", step: 1, min: 1, placeholder: "10" },
    ],
    annotations: false,
    read(task) {
      const cfg = readTaskConfig(task.id)
      const d = cfg.defaults || {}
      // Same precedence as the Python loaders and as persistTaskConfig, which
      // writes to the top level of task_config.json: top level first, then
      // defaults. Reading only defaults.* rendered a blank form for values that
      // had in fact been saved, so every edit looked like it had to be retyped.
      return {
        values: {
          protein: cfg.protein || d.protein || task.config?.protein || "",
          nCrosslinks: cfg.nCrosslinks ?? task.config?.nCrosslinks ?? 44,
          nChains: cfg.numChains ?? d.numChains ?? task.config?.nChains ?? 32,
          temperatureK: cfg.temperatureK ?? d.temperatureK
            ?? d.tempMin ?? task.config?.temperatureK ?? 310,
          strains: listToText(cfg.strains ?? task.config?.strains ?? DEFAULT_STRAINS),
          numReplicas: cfg.numReplicas ?? d.numReplicas ?? 1,
          stepsPerCycle: cfg.stepsPerCycle ?? d.stepsPerCycle ?? 500000,
          totalCycles: cfg.totalCycles ?? d.totalCycles ?? 10,
        },
        annotations: [],
      }
    },
    validate(values) {
      const nCrosslinks = num(values.nCrosslinks, { key: "Crosslinks", min: 0, step: 1, integer: true })
      const nChains = num(values.nChains, { key: "Chains", min: 1, step: 1, integer: true })
      const temperatureK = num(values.temperatureK, { key: "Temperature", min: 1 })
      // The deformation windows are a list (the generated driver samples
      // several strains per axis), entered as "0.05,0.10". Anything past 100%
      // axial strain is outside the linear-elastic regime these windows are
      // meant to measure, so it is rejected rather than submitted blindly.
      const strains = strainList(values.strains)
      if (strains === null) {
        // strainList returns null for an unparseable list; without this the
        // join below threw a TypeError and the request failed with a 500
        // instead of saying which field was wrong.
        throw new ParamError(
          "Strain windows must be a comma-separated list of positive numbers, e.g. 0.05,0.10",
          "strains",
        )
      }
      const numReplicas = num(values.numReplicas, { key: "Replicas", min: 1, step: 1, integer: true })
      const stepsPerCycle = num(values.stepsPerCycle, { key: "Steps / cycle", min: 1, step: 1, integer: true })
      const totalCycles = num(values.totalCycles, { key: "Cycles", min: 1, step: 1, integer: true })
      // GROMACS will not start a step count below its own floor, and a
      // temperature at or below zero K is not a simulation.
      if (temperatureK !== null && temperatureK < 10) {
        throw new ParamError("Temperature must be at least 10 K", "temperatureK")
      }
      return {
        values: {
          protein: str(values.protein),
          nCrosslinks: nCrosslinks ?? 44,
          nChains: nChains ?? 32,
          temperatureK: temperatureK ?? 310,
          strains: strains.join(","),
          numReplicas: numReplicas ?? 1,
          stepsPerCycle: stepsPerCycle ?? 500000,
          totalCycles: totalCycles ?? 10,
        },
        annotations: [],
      }
    },
  },
}

// Validate an uploaded field profile's header.
//
// Kept in step with check_field_csv in backend/tasktype/flow_magnetomech/main.py,
// which re-checks at synthesize time. Both are needed: this one rejects a bad
// file the moment it is uploaded, and the Python one still guards a
// synthesize run that was invoked without going through the panel.
export function checkFieldCsvHeader(content, opts = {}) {
  const heightMm = opts.heightMm
  const lines = String(content ?? "").split(/\r?\n/)
  const cols = (lines[0] ?? "").split(",").map(c => c.trim().toLowerCase()).filter(Boolean)
  if (!cols.length) {
    return { ok: false, error: "The field file is empty." }
  }
  const posMm = cols.find(c => MM_POSITION_COLUMNS.includes(c))
  const pos = posMm ?? cols.find(c => POSITION_COLUMNS.includes(c))
  const fld = cols.find(c => FIELD_COLUMNS.includes(c))
  if (!pos) {
    return {
      ok: false,
      error: `The field file needs a position column named ${POSITION_COLUMNS.join(" or ")} (metres) or ${MM_POSITION_COLUMNS[0]} (millimetres). Columns found: ${cols.join(", ")}`,
    }
  }
  if (!fld) {
    return {
      ok: false,
      error: `The field file needs a field column named ${FIELD_COLUMNS.join(" or ")}. Columns found: ${cols.join(", ")}`,
    }
  }

  // load_csv_profile interpolates over the sample height and clamps outside the
  // file's range, so positions that do not span the sample silently give a flat
  // field. That is almost always millimetres read as metres, so reject it here
  // where it can be explained instead of after a run reports a near-zero field.
  const colIndex = (lines[0] ?? "").split(",").map(c => c.trim().toLowerCase()).indexOf(pos)
  const positions = lines.slice(1)
    .map(l => l.split(",")[colIndex])
    .map(v => Number(v))
    .filter(v => Number.isFinite(v))
  if (heightMm > 0 && positions.length > 0) {
    const scale = posMm ? 1e-3 : 1.0
    const lo = Math.min(...positions) * scale
    const hi = Math.max(...positions) * scale
    const heightM = heightMm / 1e3
    const tol = Math.max(1e-12, heightM * 1e-3)
    // Either failure mode gives a silently wrong profile: a file that stops
    // short clamps to its nearest end, and one spanning far beyond the sample
    // contributes only the rows near the origin. The latter is what
    // millimetres read as metres looks like.
    const span = `${(lo * 1e3).toFixed(4)}..${(hi * 1e3).toFixed(4)} mm`
    if (lo > heightM + tol || hi < heightM - tol) {
      return {
        ok: false,
        error: `The field file positions span ${span}, which does not cover the sample `
          + `(0..${heightMm} mm); a profile taken from another origin cannot be applied to this sample.`,
      }
    }
    if (hi > heightM * 100) {
      return {
        ok: false,
        error: `The field file positions span ${span} but the sample is only ${heightMm} mm tall, `
          + `so the applied profile would be wrong. `
          + (posMm ? "" : `Rename the column to ${MM_POSITION_COLUMNS[0]} if these values are millimetres.`),
      }
    }
  }
  return { ok: true, note: `position column '${pos}'${posMm ? " (mm)" : ""}, field column '${fld}'` }
}

export function isEditableType(taskType) {
  return Object.prototype.hasOwnProperty.call(SPECS, taskType)
}

// Where a task's compute actually runs. Every quick-created task is scaffolded
// with `remoteDir`/`logPrefix` as FILL-IN strings (backend/services/task-dir.js
// writes the tasktype template verbatim) and nothing in the UI could set them,
// so a flow created from a template could not be started at all: the step
// failed with "No config dir" / "No config file found".
//
// These are deployment targets rather than science parameters, so they get their
// own panel section and are validated as paths (absolute, no shell
// metacharacters) instead of as numbers.
export const DEPLOYMENT_FIELDS = [
  {
    key: "remoteDir",
    label: "Remote working directory",
    type: "text",
    placeholder: "/home/selp/igem-2026/MD/<run name>",
    hint: "Absolute path on the server where this step's files live.",
  },
  {
    key: "logPrefix",
    label: "Log / config prefix",
    type: "text",
    placeholder: "e.g. job0",
    hint: "Prefix for this step's NAMD or GROMACS log and config files.",
  },
]

// A scaffolded FILL-IN value is a placeholder, not a setting: it must never be
// written back as if the user had chosen it, and it must block a start instead
// of being passed to the shell as a directory name.
export function isUnsetValue(v) {
  if (v === null || v === undefined) return true
  const s = String(v).trim()
  return s === "" || /^FILL-IN\b/i.test(s)
}

function deploymentValues(task) {
  const cfg = readTaskConfig(task.id)
  const remoteDir = isUnsetValue(cfg.remoteDir) ? "" : String(cfg.remoteDir).trim()
  const logPrefix = isUnsetValue(cfg.logPrefix) ? "" : String(cfg.logPrefix).trim()
  return { remoteDir, logPrefix }
}

function validateDeployment(values) {
  const remoteDir = String(values.remoteDir ?? "").trim()
  const logPrefix = String(values.logPrefix ?? "").trim()
  // Both are interpolated into shell commands on the remote host, so they are
  // checked here rather than trusted: a relative path resolves against whatever
  // directory the command happens to run in, and a metacharacter would let a
  // "directory name" run something else entirely.
  if (remoteDir && !remoteDir.startsWith("/")) {
    throw new ParamError(
      "The remote working directory must be an absolute path, e.g. /home/selp/igem-2026/MD/run1",
      "remoteDir",
    )
  }
  if (remoteDir && /[;&|`$<>\\\n]/.test(remoteDir)) {
    throw new ParamError("The remote working directory contains characters that are not allowed in a path.", "remoteDir")
  }
  if (logPrefix && !/^[\w.-]+$/.test(logPrefix)) {
    throw new ParamError(
      "The log prefix may only contain letters, digits, dot, dash and underscore.",
      "logPrefix",
    )
  }
  return { remoteDir, logPrefix }
}

// The uploaded-file descriptor for a type, or null when it takes no file.
export function fileFieldFor(taskType) {
  return SPECS[taskType]?.fileField ?? null
}

// True when the type's panel shows a motif table, so callers do not write an
// input/annotations.csv for a task that reads no motif annotations.
export function typeUsesAnnotations(taskType) {
  return !!SPECS[taskType]?.annotations
}

export function editableSpecs() {
  return Object.keys(SPECS)
}

// Build the ParamsPanel payload for an editable task type.
export function buildEditablePanel(task) {
  const spec = SPECS[task.taskType]
  if (!spec) return null
  const current = spec.read(task)
  const values = current.values || {}
  const files = current.files || {}
  const deployment = deploymentValues(task)
  // A server-backed step cannot run until both are set, so the panel says so
  // rather than leaving the user to discover it as a failed start.
  const missing = DEPLOYMENT_FIELDS
    .filter(f => isUnsetValue(deployment[f.key]))
    .map(f => f.key)
  return {
    panel: task.taskType,
    title: spec.title,
    editable: true,
    // The read-only renderer keys off fields/annotations; leaving them empty
    // is what bypasses it rather than shadowing it.
    fields: [],
    editableFields: spec.fields.map(f => ({
      ...f,
      value: values[f.key] === null || values[f.key] === undefined ? "" : String(values[f.key]),
    })),
    deploymentFields: DEPLOYMENT_FIELDS.map(f => ({ ...f, value: deployment[f.key] ?? "" })),
    deploymentMissing: missing,
    annotationRows: (current.annotations || []).map(r => ({
      sequence: r?.sequence || "",
      label: r?.label || "",
      color: r?.color || "",
    })),
    supportsAnnotations: !!spec.annotations,
    fileField: spec.fileField
      ? { ...spec.fileField, value: files[spec.fileField.key] ?? null }
      : null,
    residues: values.sequence ? String(values.sequence).length : null,
    saveEndpoint: `/api/tasks/${task.id}/params`,
    restartEndpoint: spec.restart === false ? undefined : `/api/tasks/${task.id}/restart`,
  }
}

// Validate a submission for an editable task type. Throws ParamError.
//
// Accepts either {values:{...}, annotations} or the older flat
// {protein, sequence, ..., annotations} shape, so the panel keeps working
// while the frontend and backend halves of a change roll out separately.
//
// `task` is optional but should be supplied: an omitted key is filled from the
// task's current values, so submitting one field does not blank the others.
export function validateEditable(taskType, payload = {}, task = null) {
  const spec = SPECS[taskType]
  if (!spec) {
    throw new ParamError(`Task type "${taskType}" has no editable parameters`)
  }
  const { annotations, ...flat } = payload
  const submitted = payload.values && typeof payload.values === "object" ? payload.values : flat
  // Deployment settings are accepted alongside the science parameters rather
  // than as one of `fields`, because they are validated as paths and mean
  // something different; every spec accepts them so one panel covers both.
  const known = new Set(spec.fields.map(f => f.key))
  for (const f of DEPLOYMENT_FIELDS) known.add(f.key)
  for (const key of Object.keys(submitted)) {
    if (!known.has(key)) {
      throw new ParamError(`Unknown parameter "${key}"`, key)
    }
  }
  // Fill from the task's current values so a partial submission is a partial
  // update. Previously omitted keys became "", so saving one field silently
  // cleared every other parameter -- including `strains`, which then failed to
  // parse and took the whole save down with it.
  const current = task ? (spec.read(task)?.values || {}) : {}
  const merged = {}
  for (const f of spec.fields) {
    merged[f.key] = Object.prototype.hasOwnProperty.call(submitted, f.key)
      ? submitted[f.key]
      : (current[f.key] ?? "")
  }
  const validated = spec.validate(merged, annotations, payload)
  // Only keys actually submitted are written back: a form that leaves the
  // deployment section alone must not blank a path that is already configured.
  const submittedDeployment = {}
  for (const f of DEPLOYMENT_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(submitted, f.key)) {
      submittedDeployment[f.key] = submitted[f.key]
    }
  }
  if (Object.keys(submittedDeployment).length) {
    validated.values = {
      ...validated.values,
      ...validateDeployment(submittedDeployment),
    }
  }
  return validated
}
