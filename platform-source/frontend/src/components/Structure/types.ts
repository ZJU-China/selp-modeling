export interface StructureMeta {
  stepsPerCycle?: number | null
  timestepFs?: number | null
  numReplicas?: number | null
  totalCycles?: number | null
  samples?: string[]
  generatedAt?: string
  modules?: Record<string, Record<string, unknown>>
}

export interface StructureData {
  source: string
  rg: string | null
  e2e: string | null
  rmsd: string | null
  ss: string | null
  energy: string | null
  box: string | null
  crosslink: string | null
  crosslinkTable: string | null
  chainRg: string | null
  meta: StructureMeta | null
}

/** Steps per MD cycle from the analyzer's meta.json (TIGER2 default 15000). */
export function stepsPerCycleOf(data: StructureData | null | undefined): number {
  const v = data?.meta?.stepsPerCycle
  return v && v > 0 ? v : 15000
}