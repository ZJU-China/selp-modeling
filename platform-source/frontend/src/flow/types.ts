// Shapes returned by GET /api/flows/pages and GET /api/flows/:id/overview.
// The backend normalises the five per-tasktype status dialects into TaskState
// (see backend/services/flow-overview.js) so the UI never has to.

export type TaskState = "PENDING" | "RUNNING" | "DONE" | "FAILED"

export interface TaskStatus {
  state: TaskState
  progressPct: number
  detail: string
  evidence: string
}

export interface Field {
  key: string
  label: string
  value: unknown
  suffix?: string
}

export interface SequenceAnnotations {
  present: boolean
  reason?: string
  path: string
  header?: string
  count?: number
  motifs: Array<{ sequence: string; label: string; color: string }>
}

export interface CrosslinkInfo {
  available: boolean
  reason?: string
  source?: string
  tunableVia?: string
  artefacts?: Array<{ kind: string; path: string }>
}

export interface FieldFileInfo {
  mode: string | null
  csvPath: string | null
  applicable: boolean
  reason: string | null
}

/** A parameter the Parameters panel renders as an input instead of a value. */
export interface EditableField {
  key: string
  label: string
  type: "text" | "number" | "list" | "sequence" | "select"
  value: string
  placeholder?: string
  hint?: string
  /** Unit shown next to the label (K, ε, …). */
  unit?: string
  /** Two other field keys this one is a ratio of, for a live derived readout. */
  ratioOf?: [string, string]
  ratioLabel?: string
  /** Fixed choices, for type "select". */
  options?: Array<{ value: string; label: string }>
  /**
   * Only show this field while the named fields hold one of the given values.
   * Used to keep mode-specific inputs (e.g. a gradient drop) out of the way.
   */
  when?: Record<string, string[]>
  /**
   * This field is one of the fractions that must sum to at most 1, so the form
   * can show the remainder live instead of only rejecting it on save.
   */
  partOfSum?: boolean
  /** Native input constraints, passed straight through for type "number". */
  step?: number
  min?: number
  max?: number
}

/**
 * An uploaded input file the task consumes, stored under the task's own
 * directory rather than in task_config.json.
 */
export interface EditableFileField {
  key: string
  label: string
  /** Accept attribute for the file picker, e.g. ".csv,text/csv". */
  accept?: string
  /** Task-relative directory the file is written to. */
  dir: string
  /** Path of the file currently attached, or null. */
  value: string | null
  /** Header columns the consumer needs, so a bad upload can be explained. */
  columns?: { position: string[]; field: string[] }
  /** Only offer this file while the named fields hold one of these values. */
  when?: Record<string, string[]>
}

/** One row of the motif annotation table (input/sequences.csv). */
export interface AnnotationRow {
  sequence: string
  label: string
  color: string
}

/** Result of GET /api/data/sequence-from-pdb. */
export interface DerivedChain {
  chain: string
  sequence: string
  residues: number
  unknown: Array<{ resid: number; resname: string }>
  skippedNonPolymer: number
}

export interface DerivedSequence {
  ok: boolean
  error?: string
  pdb?: string
  chains?: DerivedChain[]
  totalResidues?: number
  unknownResidues?: number
  /** Things the caller must know before trusting this sequence. */
  notes?: string[]
}

export interface ParamsPanel {
  panel: "tiger2" | "gromacs_cg" | "magnetomech" | "transition" | "flow_tiger2" | "flow_gromacs_cg" | "flow_magnetomech"
  title: string
  fields: Field[]
  annotations?: SequenceAnnotations
  crosslink?: CrosslinkInfo
  fieldFile?: FieldFileInfo
  /** Set when the panel is an input form the user can edit and save. */
  editable?: boolean
  editableFields?: EditableField[]
  /**
   * Where the step runs: remote directory and log/config prefix. These are
   * deployment targets rather than science parameters, so they are validated as
   * paths and rendered in their own section.
   */
  deploymentFields?: EditableField[]
  /** Keys of the deployment fields that are still unset. */
  deploymentMissing?: string[]
  annotationRows?: AnnotationRow[]
  /** False for editable panels whose task consumes no motif table. */
  supportsAnnotations?: boolean
  /** Set when the panel uploads a file the task consumes. */
  fileField?: EditableFileField | null
  residues?: number | null
  saveEndpoint?: string
  restartEndpoint?: string
}

export interface Artifacts {
  structure: Array<{ key: string; label: string; unit: string }>
  meta: Record<string, unknown> | null
  trajectory: { frames: string[]; topology: string[]; source: string } | null
  magnetomech: boolean
  magnetomechImage: boolean
  convergence: boolean
  temperature: boolean
}

export interface ControlDef {
  id: string
  label: string
  kind: "run" | "view"
  endpoint?: string
  method?: string
  view?: string
}

/** Where a step actually runs, and how its external tools are invoked. */
export interface Execution {
  connection: {
    mode: "local" | "ssh" | "unresolved"
    label: string
    host: string | null
    port: number | null
    username: string | null
    namdBin: string | null
  }
  paths: {
    base: string
    input: string
    output: string
    remoteWorkDir: string | null
  }
  tools: Record<string, ToolResolution> | null
}

export interface ToolResolution {
  name: string
  ok: boolean
  command?: string
  argv?: string[]
  resolvedTo?: string | null
  viaContainer?: boolean
  error?: string
}

export interface FlowTask {
  index: number
  id: string
  name: string
  taskType: string
  isTransition: boolean
  isLocal: boolean
  status: TaskStatus
  params: ParamsPanel
  artifacts: Artifacts
  controls: ControlDef[]
  workDir: string | null
  execution?: Execution
}

export interface FlowProgress {
  total: number
  doneCount: number
  currentIndex: number
  currentTaskId: string | null
  currentTaskName: string | null
  /** Furthest step that has started work; drives the progress bar width. */
  reachedIndex: number
  reachedTaskName: string | null
  /** True when an earlier step is still running behind a later finished one. */
  outOfOrder: boolean
  clearedPct: number
  stepPct: number
  complete: boolean
  steps: Array<{ id: string; name: string; taskType: string; state: TaskState; progressPct: number }>
}

export interface FlowOverview {
  flow: { id: string; name: string; createdAt: number }
  progress: FlowProgress
  tasks: FlowTask[]
  folder: string
  folderPath: string
  sourceOfTruth: string
}

export interface FlowListEntry {
  id: string
  name: string
  createdAt: number
  taskCount: number
  folder: string
  progress: FlowProgress
}

export const TASK_STATE_STYLE: Record<TaskState, { label: string; badge: string }> = {
  PENDING: { label: "Pending", badge: "badge-warning" },
  RUNNING: { label: "Running", badge: "badge-info" },
  DONE: { label: "Done", badge: "badge-success" },
  FAILED: { label: "Failed", badge: "badge-danger" },
}

export const TASK_TYPE_LABEL: Record<string, string> = {
  tiger2: "TIGER2 (all-atom MD)",
  "tiger2-convergence": "TIGER2 (convergence)",
  // The flow_* types are the pipeline steps. They run the same engine as their
  // standalone counterpart but regenerate their inputs from the Parameters panel
  // on every start, so they are labelled by what the step contributes. flow_tiger2
  // also folds in the DCD -> CG conversion, so it hands the CG step its start
  // structure.
  flow_tiger2: "TIGER2 (all-atom MD → CG start)",
  gromacs_cg: "GROMACS (coarse-grained)",
  flow_gromacs_cg: "GROMACS (coarse-grained)",
  magnetomech: "Magnetomechanics (local)",
  flow_magnetomech: "Magnetomechanics (composite + field)",
  seq_to_pdb: "Sequence → PDB",
  tiger2_dcd_to_gromacs_cg_pdb: "DCD → CG PDB",
}
