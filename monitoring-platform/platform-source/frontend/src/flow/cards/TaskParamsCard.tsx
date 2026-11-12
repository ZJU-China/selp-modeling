import { useState } from "react"
import type { AnnotationRow, DerivedSequence, EditableField, EditableFileField, FlowTask, ParamsPanel } from "../types"
import {
  downloadTextFile,
  fetchSequenceFromPdb,
  readTaskFile,
  runControl,
  saveTaskParams,
  uploadTaskFile,
} from "../api"

// Aggregated parameter panel for one step. The layout is driven by the
// tasktype-specific `panel` discriminator the backend attaches, so a new
// tasktype gets a sensible fallback rather than an empty card.
export function TaskParamsCard({
  params,
  taskId,
  siblings,
}: {
  params: ParamsPanel
  taskId?: string
  siblings?: FlowTask[]
}) {
  if (params.editable && params.editableFields) {
    return (
      <EditableParamsForm
        params={params}
        taskId={taskId}
        fields={params.editableFields}
        deploymentFields={params.deploymentFields ?? []}
        deploymentMissing={params.deploymentMissing ?? []}
        rows={params.annotationRows ?? []}
        fileField={params.fileField ?? null}
        siblings={(siblings ?? []).filter(t => t.id !== taskId)}
      />
    )
  }

  return (
    <div className="flow-panel">
      <div className="flow-panel-head">
        <h4 className="flow-panel-title">{params.title}</h4>
      </div>

      {params.fields.length > 0 && (
        <dl className="flow-kv">
          {params.fields.map(f => (
            <div className="flow-kv-row" key={f.key}>
              <dt>{f.label}</dt>
              <dd>
                {f.value === null || f.value === undefined || f.value === ""
                  ? <span className="flow-none">not set</span>
                  : <>{String(f.value)}{f.suffix ? <span className="flow-suffix"> {f.suffix}</span> : null}</>}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {params.annotations && <AnnotationTable ann={params.annotations} />}

      {params.crosslink && <CrosslinkPanel info={params.crosslink} />}

      {params.fieldFile && <FieldFilePanel info={params.fieldFile} />}

      {params.fields.length === 0 && !params.annotations && !params.crosslink && !params.fieldFile && (
        <div className="empty-state">No parameters recorded for this step.</div>
      )}
    </div>
  )
}

// TIGER2 input sequence + annotation table, read from input/sequences.csv.
function AnnotationTable({ ann }: { ann: NonNullable<ParamsPanel["annotations"]> }) {
  if (!ann.present) {
    return (
      <div className="flow-subpanel">
        <div className="flow-subpanel-title">Input sequence &amp; annotation table</div>
        <div className="flow-note flow-note-muted">
          Not provided. No <code>{ann.path}</code> for this task, so there is no motif
          annotation table to show. Add one to label motifs in the structure viewer.
        </div>
      </div>
    )
  }
  return (
    <div className="flow-subpanel">
      <div className="flow-subpanel-title">
        Input sequence &amp; annotation table
        <span className="flow-subpanel-meta">{ann.count} motif{ann.count === 1 ? "" : "s"} · {ann.path}</span>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Label</th>
            <th>Sequence</th>
            <th>Length</th>
            <th>Color</th>
          </tr>
        </thead>
        <tbody>
          {ann.motifs.map((m, i) => (
            <tr key={`${m.sequence}-${i}`}>
              <td>{m.label}</td>
              <td><code className="flow-seq">{m.sequence}</code></td>
              <td>{m.sequence.length} aa</td>
              <td>
                <span className="flow-swatch" style={{ background: m.color || "#999" }} />
                <code className="flow-hex">{m.color || "auto"}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// GROMACS CG crosslink degree.
//
// The backend has no crosslink parameter and this task produced no crosslink
// artefact, so this states the reason and where the number actually lives
// rather than showing a blank or an invented figure.
function CrosslinkPanel({ info }: { info: NonNullable<ParamsPanel["crosslink"]> }) {
  if (!info.available) {
    return (
      <div className="flow-subpanel">
        <div className="flow-subpanel-title">Crosslink degree</div>
        <div className="flow-note flow-note-warn">
          <strong>Not a per-task parameter.</strong> {info.reason}
          {info.source && <div className="flow-note-detail">Defined by: <code>{info.source}</code></div>}
          {info.tunableVia && <div className="flow-note-detail">Currently settable only via: <code>{info.tunableVia}</code></div>}
        </div>
      </div>
    )
  }
  return (
    <div className="flow-subpanel">
      <div className="flow-subpanel-title">Crosslink degree</div>
      <ul className="flow-plain-list">
        {info.artefacts?.map(a => <li key={a.path}><code>{a.path}</code></li>)}
      </ul>
    </div>
  )
}

// Magnetomech "input magnetic field file".
//
// Only meaningful when field.mode === "csv". For uniform/gradient the profile
// is generated from parameters, so there is no file to show and saying so is
// more useful than an empty slot.
function FieldFilePanel({ info }: { info: NonNullable<ParamsPanel["fieldFile"]> }) {
  return (
    <div className="flow-subpanel">
      <div className="flow-subpanel-title">Applied field profile</div>
      <dl className="flow-kv flow-kv-tight">
        <div className="flow-kv-row">
          <dt>Mode</dt>
          <dd>{info.mode ?? <span className="flow-none">not set</span>}</dd>
        </div>
        <div className="flow-kv-row">
          <dt>Field file</dt>
          <dd>
            {info.applicable
              ? (info.csvPath
                ? <code>{info.csvPath}</code>
                : <span className="flow-none">csv mode selected but no path set</span>)
              : <span className="flow-none">not applicable</span>}
          </dd>
        </div>
      </dl>
      {info.reason && <div className="flow-note flow-note-muted">{info.reason}</div>}
    </div>
  )
}

const PALETTE = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4"]

const STANDARD_AA = "ACDEFGHIKLMNPQRSTVWY"

function normaliseSequence(raw: string): string {
  return raw.replace(/[^A-Za-z]/g, "").toUpperCase()
}

// Mirrors _find_all in backend/_shared/sequence_annotation.py: every
// occurrence, including overlapping ones.
function countOccurrences(hay: string, needle: string): number {
  if (!needle) return 0
  let n = 0
  let i = hay.indexOf(needle)
  while (i !== -1) {
    n++
    i = hay.indexOf(needle, i + 1)
  }
  return n
}

function isHex(value: string): boolean {
  return /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(value)
}

function formatBytes(n: number): string {
  if (!Number.isFinite(n) || n < 0) return "unknown size"
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

// Upload / download slot for an input file the task consumes.
//
// The accepted columns are named here because the consumer skips rows it
// cannot read, so a profile with the wrong header produces a silently empty
// field rather than an error until Save is pressed.
function FileSlot({
  field,
  taskId,
  path,
  downloading,
  onPick,
  onDownload,
}: {
  field: EditableFileField
  taskId?: string
  path: string | null
  downloading: boolean
  onPick: (f: File | null) => void
  onDownload: () => void
}) {
  const cols = field.columns
  return (
    <div className="flow-subpanel">
      <div className="flow-subpanel-title">
        {field.label}
        <span className="flow-subpanel-meta">
          {cols
            ? `needs a position column (${cols.position.join(" or ")}) and a field column (${cols.field.join(" or ")})`
            : `stored in ${field.dir}/`}
        </span>
      </div>

      <div className="flow-file-row">
        <label className={`btn btn-sm flow-file-pick ${!taskId ? "is-disabled" : ""}`}>
          Upload
          <input
            type="file"
            accept={field.accept}
            disabled={!taskId}
            onChange={e => {
              onPick(e.target.files?.[0] ?? null)
              // Allow re-picking the same file after a failed validation.
              e.target.value = ""
            }}
          />
        </label>
        <button
          type="button"
          className="btn btn-sm"
          disabled={!path || downloading}
          onClick={onDownload}
        >
          {downloading ? "Reading…" : "Download"}
        </button>
        <span className="flow-file-name">
          {path ? <code>{path.split("/").pop()}</code> : <span className="flow-none">no file attached</span>}
        </span>
      </div>
    </div>
  )
}

// Editable input form for any task type listed in the backend's editable-params
// specs (currently flow_tiger2 and flow_gromacs_cg).
//
// This replaces the read-only summary for those types: the user fills in the
// fields, saves, and restarts. Saving writes the values to scripts/task_config.json
// (and input/annotations.csv where relevant); restarting re-derives the task's
// inputs from them before handing off to the underlying runner, so an edited
// value is never silently ignored by a stale file.
//
// Which fields appear comes from the backend spec, so a new editable task type
// needs no change here.
function EditableParamsForm({
  params,
  taskId,
  fields,
  deploymentFields,
  deploymentMissing,
  rows,
  fileField,
  siblings,
}: {
  params: ParamsPanel
  taskId?: string
  fields: EditableField[]
  deploymentFields: EditableField[]
  deploymentMissing: string[]
  rows: AnnotationRow[]
  fileField: EditableFileField | null
  siblings: FlowTask[]
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map(f => [f.key, f.value ?? ""])),
  )
  // Held apart from `values` because the backend validates these as paths
  // rather than as parameters, and because they are what the user needs set
  // before a start can work at all.
  const [deployment, setDeployment] = useState<Record<string, string>>(() =>
    Object.fromEntries(deploymentFields.map(f => [f.key, f.value ?? ""])),
  )
  const [motifs, setMotifs] = useState<AnnotationRow[]>(() => rows.map(r => ({ ...r })))
  const [attached, setAttached] = useState<Record<string, string | null>>(() =>
    fileField ? { [fileField.key]: fileField.value ?? null } : {},
  )
  const [uploadNote, setUploadNote] = useState<{ kind: "ok" | "error"; text: string } | null>(null)
  const [downloading, setDownloading] = useState(false)
  const [busy, setBusy] = useState<null | "save" | "restart">(null)
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null)

  const [deriveFrom, setDeriveFrom] = useState("")
  const [deriveBusy, setDeriveBusy] = useState(false)
  const [derived, setDerived] = useState<DerivedSequence | null>(null)

  // Panels are shaped by what the task actually consumes: only the sequence
  // panels get AA validation, the derive tool, and the motif table.
  const hasSequence = fields.some(f => f.type === "sequence")
  const hasAnnotations = params.supportsAnnotations !== false
  const sequence = normaliseSequence(values.sequence ?? "")
  const unsupported = hasSequence
    ? [...new Set(sequence.split("").filter(c => !STANDARD_AA.includes(c)))]
    : []

  // A field gated by `when` is hidden unless the fields it names currently hold
  // one of the listed values, so mode-specific inputs stay out of the way.
  const visible = (f: EditableField | EditableFileField) =>
    !f.when || Object.entries(f.when).every(([k, allowed]) => allowed.includes(values[k] ?? ""))
  const shownFields = fields.filter(visible)

  // Volume fractions that must leave room for the remainder. Showing the
  // remainder live means an over-full set is visible before saving rather than
  // only in the server's error message.
  const sumKeys = fields.filter(f => f.partOfSum).map(f => f.key)
  const entered = sumKeys
    .map(k => Number(values[k]))
    .filter(n => Number.isFinite(n))
  const sumTotal = sumKeys.length > 0 ? entered.reduce((a, b) => a + b, 0) : 0
  const remainder = 1 - sumTotal
  const sumComplete = entered.length === sumKeys.length

  const setField = (key: string, value: string) =>
    setValues(v => ({ ...v, [key]: value }))

  const setDeployField = (key: string, value: string) =>
    setDeployment(v => ({ ...v, [key]: value }))

  // Checked in the form as well as on the server, so the reason a start failed
  // is visible before it is attempted. A relative path would resolve against
  // whatever directory the remote command happens to run in.
  const deployPathIssue = (() => {
    const dir = (deployment.remoteDir ?? "").trim()
    if (dir && !dir.startsWith("/")) return "The remote working directory must be an absolute path, starting with /."
    if (dir && /[;&|`$<>\\\n]/.test(dir)) return "The remote working directory cannot contain ; & | ` $ < > or \\."
    const prefix = (deployment.logPrefix ?? "").trim()
    if (prefix && !/^[\w.-]+$/.test(prefix)) return "The log prefix may only contain letters, digits, dot, dash and underscore."
    return null
  })()

  const deploymentReady = deploymentMissing.length === 0 && deployPathIssue === null

  const updateRow = (i: number, patch: Partial<AnnotationRow>) =>
    setMotifs(rows => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  const addRow = () =>
    setMotifs(rows => [
      ...rows,
      { sequence: "", label: "", color: PALETTE[rows.length % PALETTE.length] },
    ])

  const removeRow = (i: number) => setMotifs(rows => rows.filter((_, j) => j !== i))

  const fileReady = !fileField || !visible(fileField) || Boolean(attached[fileField.key])
  const canSubmit =
    Boolean(taskId) &&
    (!hasSequence || (sequence.length > 0 && unsupported.length === 0)) &&
    remainder >= -1e-9 &&
    fileReady

  // A field may name two other fields it is a ratio of (crosslinks per chain),
  // so the derived value updates as the user types instead of only after a save.
  const derivedNotes = fields.flatMap(f => {
    if (!f.ratioOf) return []
    const [numKey, denKey] = f.ratioOf
    const numerator = Number(values[numKey])
    const denominator = Number(values[denKey])
    if (!(numerator > 0) || !(denominator > 0)) return []
    const ratio = numerator / denominator
    // Show it compactly when two decimals already tell the whole story
    // (1.375 -> 1.38), otherwise keep three.
    return [`${Math.round(ratio * 100) / 100 === ratio ? ratio : ratio.toFixed(3)} ${
      f.ratioLabel ?? `per ${denKey}`
    }`]
  })

  function loadChain(chainName: string, seq: string, count: number, source: string) {
    setField("sequence", seq)
    setMessage({
      kind: "ok",
      text: `Loaded ${count} residues from ${source} (chain ${chainName}). Review the sequence, then save.`,
    })
  }

  // Reverse a sibling task's PDB back into its sequence.
  //
  // A TIGER2 task built from a prebuilt topology often stores its sequence
  // nowhere, so the structure is the only record. This recovers the sequence
  // only -- rebuilding from it produces a fresh extended chain, not the
  // original fold, which is why the result is always shown for review.
  async function derive() {
    if (!deriveFrom) return
    setDeriveBusy(true)
    setDerived(null)
    setMessage(null)
    try {
      const r = await fetchSequenceFromPdb(deriveFrom)
      setDerived(r)
      const chains = r.chains ?? []
      if (!r.ok || chains.length === 0) return
      if (chains.length === 1) {
        const c = chains[0]
        loadChain(c.chain, c.sequence, c.residues, r.pdb ?? "structure")
      }
    } catch (e) {
      setDerived({ ok: false, error: e instanceof Error ? e.message : String(e) })
    } finally {
      setDeriveBusy(false)
    }
  }

  // Upload the attached file into the task's input directory.
  //
  // The server does not parse the file here: it checks the header when the
  // values are saved, so that is the step that reports an unusable profile.
  async function onPickFile(file: File | null) {
    if (!taskId || !fileField || !file) return
    setUploadNote(null)
    try {
      const content = await file.text()
      const path = `${fileField.dir}/${file.name}`
      const { bytes } = await uploadTaskFile(taskId, path, content)
      setAttached(a => ({ ...a, [fileField.key]: path }))
      setUploadNote({
        kind: "ok",
        text: `Uploaded ${file.name} (${formatBytes(bytes)}) to ${path}. Save to attach it to the run.`,
      })
    } catch (e) {
      setUploadNote({ kind: "error", text: e instanceof Error ? e.message : String(e) })
    }
  }

  async function onDownloadFile() {
    if (!taskId || !fileField) return
    const path = attached[fileField.key]
    if (!path) return
    setDownloading(true)
    try {
      downloadTextFile(path.split("/").pop() || "field_profile.csv", await readTaskFile(taskId, path))
    } catch (e) {
      setUploadNote({ kind: "error", text: e instanceof Error ? e.message : String(e) })
    } finally {
      setDownloading(false)
    }
  }

  async function save(): Promise<boolean> {
    if (!taskId) return false
    setBusy("save")
    setMessage(null)
    setUploadNote(null)
    try {
      // Deployment keys ride along in `values`; the backend splits them back out and
      // validates them as paths.
      await saveTaskParams(taskId, {
        values: { ...values, ...deployment },
        annotations: motifs,
        files: attached,
      })
      setMessage({
        kind: "ok",
        text: deploymentReady
          ? (hasSequence
            ? "Saved. Restart the step to rebuild the structure and re-run TIGER2 from these values."
            : "Saved. Restart the step to regenerate the run inputs from these values.")
          : "Saved. This step still cannot start until its remote working directory and log prefix are set.",
      })
      return true
    } catch (e) {
      setMessage({ kind: "error", text: e instanceof Error ? e.message : String(e) })
      return false
    } finally {
      setBusy(null)
    }
  }

  async function saveAndRestart() {
    if (!params.restartEndpoint) {
      await save()
      return
    }
    if (!(await save())) return
    setBusy("restart")
    const r = await runControl(params.restartEndpoint)
    setMessage(
      r.ok
        ? { kind: "ok", text: "Saved and restarted." }
        : { kind: "error", text: r.error ?? "Restart failed" },
    )
    setBusy(null)
  }

  return (
    <div className="flow-panel">
      <div className="flow-panel-head">
        <h4 className="flow-panel-title">{params.title}</h4>
        <span className="flow-panel-meta">
          {hasSequence
            ? sequence.length > 0
              ? `${sequence.length} residues`
              : "no sequence yet"
            : (sumKeys.length > 0 && sumComplete
              ? `water ${remainder.toFixed(3)}`
              : derivedNotes[0] ?? "")}
        </span>
      </div>

      {!taskId && (
        <div className="flow-note flow-note-warn">This panel is read-only: the step has no task id.</div>
      )}

      <div className="flow-form">
        {shownFields.map(f => (
          <label className="flow-form-field" key={f.key}>
            <span className="flow-form-label">
              {f.label}
              {f.unit && <span className="flow-form-unit"> ({f.unit})</span>}
            </span>
            {f.type === "sequence" ? (
              <textarea
                className="flow-input flow-textarea"
                rows={3}
                spellCheck={false}
                value={values[f.key] ?? ""}
                placeholder={f.placeholder}
                onChange={e => setField(f.key, e.target.value)}
              />
            ) : f.type === "select" ? (
              <select
                className="flow-input"
                value={values[f.key] ?? ""}
                onChange={e => setField(f.key, e.target.value)}
              >
                {(f.options ?? []).map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            ) : (
              <input
                className="flow-input"
                type={f.type === "number" ? "number" : "text"}
                step={f.step}
                min={f.min}
                max={f.max}
                value={values[f.key] ?? ""}
                placeholder={f.placeholder}
                spellCheck={false}
                inputMode={f.type === "number" ? "decimal" : undefined}
                onChange={e => setField(f.key, e.target.value)}
              />
            )}
            {derivedNotes.length > 0 && f.ratioOf && (
              <span className="flow-form-hint">
                {derivedNotes[0]} &mdash; this is the crosslink density the network is
                prepared to match.
              </span>
            )}
            {!f.ratioOf && f.hint && <span className="flow-form-hint">{f.hint}</span>}
          </label>
        ))}
      </div>

      {deploymentFields.length > 0 && (
      <div className="flow-subpanel">
        <div className="flow-subpanel-title">
          Where this step runs
          <span className="flow-subpanel-meta">
            {deploymentReady ? "configured" : "needed before this step can start"}
          </span>
        </div>

        {!deploymentReady && (
          <div className="flow-note flow-note-warn">
            A new step has a placeholder working directory, so starting it fails with
            &ldquo;No config dir&rdquo;. Set both fields below and save.
          </div>
        )}

        <div className="flow-form">
          {deploymentFields.map(f => (
            <label className="flow-form-field" key={f.key}>
              <span className="flow-form-label">{f.label}</span>
              <input
                className="flow-input"
                type="text"
                value={deployment[f.key] ?? ""}
                placeholder={f.placeholder}
                spellCheck={false}
                onChange={e => setDeployField(f.key, e.target.value)}
              />
              {f.hint && <span className="flow-form-hint">{f.hint}</span>}
            </label>
          ))}
        </div>

        {deployPathIssue && (
          <div className="flow-note flow-note-warn">{deployPathIssue}</div>
        )}
      </div>
      )}

      {sumKeys.length > 0 && (
        <div className={`flow-note ${remainder < -1e-9 ? "flow-note-warn" : "flow-note-muted"}`}>
          {remainder < -1e-9 ? (
            <>
              These fractions add up to <strong>{sumTotal.toFixed(4)}</strong>, leaving{" "}
              <strong>{remainder.toFixed(4)}</strong> for water. Their sum must not exceed 1.
            </>
          ) : sumComplete ? (
            <>
              Solid phases {sumTotal.toFixed(4)} + water <strong>{remainder.toFixed(4)}</strong>{" "}
              = 1.0000. Water is the remainder and is set for you.
            </>
          ) : (
            <>
              Fractions entered so far total {sumTotal.toFixed(4)}; water takes the rest.
            </>
          )}
        </div>
      )}

      {fileField && visible(fileField) && (
        <FileSlot
          field={fileField}
          taskId={taskId}
          path={attached[fileField.key] ?? null}
          downloading={downloading}
          onPick={onPickFile}
          onDownload={onDownloadFile}
        />
      )}

      {uploadNote && (
        <div className={`flow-note ${uploadNote.kind === "ok" ? "flow-note-ok" : "flow-note-warn"}`}>
          {uploadNote.text}
        </div>
      )}

      {unsupported.length > 0 && (
        <div className="flow-note flow-note-warn">
          Unsupported amino-acid code{unsupported.length > 1 ? "s" : ""}:{" "}
          <code>{unsupported.join(", ")}</code>
        </div>
      )}

      {hasSequence && (
      <div className="flow-subpanel">
        <div className="flow-subpanel-title">
          Derive sequence from an existing structure
          <span className="flow-subpanel-meta">recovers the sequence from another step&apos;s PDB</span>
        </div>

        {siblings.length === 0 ? (
          <div className="flow-note flow-note-muted">
            No other step in this flow to read a structure from.
          </div>
        ) : (
          <div className="flow-derive-row">
            <select
              className="flow-input"
              value={deriveFrom}
              onChange={e => { setDeriveFrom(e.target.value); setDerived(null) }}
            >
              <option value="">Select a step…</option>
              {siblings.map(s => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.taskType}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!deriveFrom || deriveBusy}
              onClick={() => void derive()}
            >
              {deriveBusy ? "Reading…" : "Derive"}
            </button>
          </div>
        )}

        {derived && !derived.ok && (
          <div className="flow-note flow-note-warn">{derived.error}</div>
        )}

        {derived?.ok && (
          <>
            <div className="flow-note flow-note-muted">
              Read <code>{derived.pdb}</code> — {derived.totalResidues} residue
              {derived.totalResidues === 1 ? "" : "s"}
              {derived.unknownResidues ? `, ${derived.unknownResidues} non-standard` : ""}.
              {derived.chains && derived.chains.length > 1 && " Choose a chain:"}
            </div>

            {derived.chains && derived.chains.length > 1 && (
              <div className="flow-derive-chains">
                {derived.chains.map(c => (
                  <button
                    key={c.chain}
                    type="button"
                    className="btn btn-sm"
                    onClick={() => loadChain(c.chain, c.sequence, c.residues, derived.pdb ?? "structure")}
                  >
                    Use chain {c.chain} ({c.residues} aa)
                  </button>
                ))}
              </div>
            )}

            {derived.notes?.map((n, i) => (
              <div className="flow-note flow-note-warn" key={i}>{n}</div>
            ))}

            <div className="flow-note flow-note-muted">
              This recovers the sequence only. Saving and restarting rebuilds a fresh
              extended chain from it — not the original folded structure.
            </div>
          </>
        )}
      </div>

      )}
      {hasAnnotations && (
      <div className="flow-subpanel">
        <div className="flow-subpanel-title">
          Motif annotations
          <span className="flow-subpanel-meta">
            colours every occurrence of each motif in the trajectory
          </span>
        </div>

        {motifs.length === 0 ? (
          <div className="flow-note flow-note-muted">
            No motifs. The trajectory will render without highlight regions.
          </div>
        ) : (
          <table className="data-table flow-edit-table">
            <thead>
              <tr>
                <th>Label</th>
                <th>Motif</th>
                <th>Matches</th>
                <th>Color</th>
                <th aria-label="Remove" />
              </tr>
            </thead>
            <tbody>
              {motifs.map((r, i) => {
                const motif = normaliseSequence(r.sequence)
                const hits = countOccurrences(sequence, motif)
                const swatch = isHex(r.color) ? r.color : PALETTE[i % PALETTE.length]
                return (
                  <tr key={i}>
                    <td>
                      <input
                        className="flow-input flow-input-sm"
                        value={r.label}
                        placeholder={motif || "label"}
                        onChange={e => updateRow(i, { label: e.target.value })}
                      />
                    </td>
                    <td>
                      <input
                        className="flow-input flow-input-sm flow-input-mono"
                        value={r.sequence}
                        placeholder="ACDEF"
                        spellCheck={false}
                        onChange={e => updateRow(i, { sequence: e.target.value })}
                      />
                    </td>
                    <td className="flow-num">
                      {motif ? (
                        hits > 0 ? (
                          <span title={`${hits} occurrence(s) in the sequence`}>{hits}×</span>
                        ) : (
                          <span className="flow-warn-inline" title="This motif does not occur in the sequence, so it would highlight nothing.">
                            0×
                          </span>
                        )
                      ) : (
                        <span className="flow-none">—</span>
                      )}
                    </td>
                    <td>
                      <span className="flow-color-cell">
                        <input
                          type="color"
                          className="flow-color-input"
                          value={swatch}
                          onChange={e => updateRow(i, { color: e.target.value })}
                        />
                        <input
                          className="flow-input flow-input-sm flow-input-mono"
                          value={r.color}
                          placeholder="auto"
                          spellCheck={false}
                          onChange={e => updateRow(i, { color: e.target.value })}
                        />
                      </span>
                    </td>
                    <td>
                      <button type="button" className="btn btn-sm" onClick={() => removeRow(i)}>
                        Remove
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        <button type="button" className="btn btn-sm" onClick={addRow}>
          Add motif
        </button>
      </div>
      )}

      {message && (
        <div className={`flow-note ${message.kind === "ok" ? "flow-note-ok" : "flow-note-warn"}`}>
          {message.text}
        </div>
      )}

      <div className="flow-form-actions">
        <button
          type="button"
          className="btn btn-sm"
          disabled={!canSubmit || busy !== null}
          onClick={() => void save()}
        >
          {busy === "save" ? "Saving…" : "Save"}
        </button>
        {params.restartEndpoint && (
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={!canSubmit || busy !== null}
            onClick={() => void saveAndRestart()}
          >
            {busy === "restart" ? "Restarting…" : "Save & restart"}
          </button>
        )}
      </div>
    </div>
  )
}
