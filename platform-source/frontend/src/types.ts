export interface NextLinkFile { output: string; into: string }
export interface NextLink { toTaskId: string; files?: NextLinkFile[] }

export interface TaskConfig {
  id: string
  name: string
  serverId: string
  serverName: string
  workDir: string
  scriptName?: string
  taskType?: string
  config?: Record<string, any>
  next?: NextLink[]
  connected: boolean
  running?: boolean
  flowId?: string
  flowName?: string
  createdAt?: number
}

export interface Flow {
  id: string
  name: string
  createdAt?: number
  taskCount?: number
}

export type Page = "dashboard" | "temperature" | "structure" | "cluster" | "tasks" | "convergence" | "magnetomech"

export const TASK_TYPES: { id: string; label: string; transition?: boolean; local?: boolean }[] = [
  { id: "tiger2", label: "TIGER2 (Replica Exchange)" },
  { id: "tiger2-convergence", label: "TIGER2 Convergence" },
  { id: "flow_tiger2", label: "TIGER2 (Sequence → MD → CG input)" },
  { id: "flow_gromacs_cg", label: "GROMACS CG (CG network → deformation run)" },
  { id: "gromacs_cg", label: "GROMACS CG (Martini)" },
  { id: "seq_to_pdb", label: "Sequence → Extended PDB (Transition)", transition: true },
  { id: "tiger2_dcd_to_gromacs_cg_pdb", label: "TIGER2 DCD → GROMACS CG PDB (Transition)", transition: true },
  { id: "magnetomech", label: "Magnetomech (Field Deformation)", local: true },
  { id: "flow_magnetomech", label: "Magnetomech (Composite Fractions + Field)", local: true },
]

export const TASK_TYPE_LABEL: Record<string, string> = Object.fromEntries(TASK_TYPES.map(t => [t.id, t.label]))

// Transitional tasks: local file generators, only visible inside Task Control.
export const TRANSITION_TASK_TYPES = new Set(
  TASK_TYPES.filter(t => t.transition).map(t => t.id)
)

// Local ("no-server") task types: compute runs entirely on the backend host
// (never SSH), so creating them does not require selecting a server. Mirrors
// backend/store.js LOCAL_TASK_TYPES.
export const LOCAL_TASK_TYPES = new Set(
  TASK_TYPES.filter(t => t.local).map(t => t.id)
)

export function parseTimeSeries(raw: string, valueKey: string): { step: number; [k: string]: number }[] {
  if (!raw) return []
  const lines = raw.trim().split("\n").filter(l => l.trim() && !l.startsWith("#"))
  return lines.map(line => {
    const parts = line.trim().split(/[\s,\t]+/)
    const step = Number(parts[0]) || 0
    const val = Number(parts[1]) || 0
    return { step, [valueKey]: val }
  }).filter(d => d.step > 0)
}

export function parseReplicaData(raw: string): { replica: number; frame: number; value: number }[] {
  if (!raw) return []
  const lines = raw.trim().split("\n").filter(l => l.trim() && !l.startsWith("#"))
  const result: { replica: number; frame: number; value: number }[] = []
  const frameCounters: Record<number, number> = {}
  for (const line of lines) {
    const parts = line.trim().split(/[\s,\t]+/)
    const replica = Number(parts[0])
    if (isNaN(replica)) continue
    const val = Number(parts[2]) || 0
    const step = Number(parts[1]) || 0
    if (step <= 0) continue
    if (frameCounters[replica] === undefined) frameCounters[replica] = 0
    result.push({ replica, frame: frameCounters[replica]++, value: val })
  }
  return result
}

export const FS_TO_NS = 0.000004
export const POLL_INTERVAL_MS = 60_000
export const TASK_POLL_INTERVAL_MS = 10_000
export const MESSAGE_TIMEOUT_MS = 4_000
