// Shared parsing for the local analysis .dat/.tsv files produced by the
// backend analyzer (tab/space separated, `#`-prefixed comment lines).

export interface ReplicaPoint {
  replica: number
  step: number
  cycle: number
  value: number
}

/** Non-comment data rows of a .dat/.tsv file. */
export function datRows(raw: string | null | undefined): string[][] {
  if (!raw) return []
  return raw
    .trim()
    .split("\n")
    .map(line => line.trim())
    .filter(line => line && !line.startsWith("#"))
    .map(line => line.split(/[\s\t,]+/).filter(Boolean))
}

/** The `# replica step <value...>` row set, as { replica, step, cycle, value }
 *  using parts[1] (step) and parts[2] (value). Frames at step 0 are skipped. */
export function parseReplicaSeries(raw: string | null | undefined, stepsPerCycle: number): ReplicaPoint[] {
  const out: ReplicaPoint[] = []
  for (const parts of datRows(raw)) {
    const replica = Number(parts[0])
    const step = Number(parts[1])
    if (isNaN(replica) || isNaN(step) || step <= 0) continue
    const value = Number(parts[2])
    if (isNaN(value)) continue
    out.push({ replica, step, cycle: Math.round(step / stepsPerCycle), value })
  }
  return out
}

/** Distinct 0-based replica ids present in a raw .dat file (sorted). */
export function replicaIds(raw: string | null | undefined): number[] {
  const set = new Set<number>()
  for (const parts of datRows(raw)) {
    const r = Number(parts[0])
    if (!isNaN(r)) set.add(r)
  }
  return [...set].sort((a, b) => a - b)
}

/** X axis ticks for a cycle-based line chart (every 100 cycles). */
export function cycleTicks(cycles: number[]): number[] {
  const max = Math.max(1, ...cycles)
  return Array.from({ length: Math.floor(max / 100) + 2 }, (_, i) => i * 100)
}