import { useEffect, useState } from "react"
import { MolecularViewer } from "../MolecularViewer"
import type { StructureData } from "./types"

interface TrajectoryStatus {
  samples?: string[]
  dcdSizes?: number[]
  last100Frames?: number[]
  generatedAt?: number
}

function shortLabel(sample: string): string {
  // "positive33_xy_m100_s01" -> "xy m100" (drop batch prefix + sample index)
  const m = sample.match(/^(?:positive33|negative33|tensile)[_-]?([^_]+)_(m\d+|p\d+|r\d+)/)
  return m ? `${m[1]} ${m[2]}` : sample
}

export function TrajectoryTab({ taskId, defaultReplicas = [0, 1, 2, 3] }: {
  data: StructureData
  taskId: string
  /** Replica buttons shown before the trajectory status is available, and the
   *  fallback when the status carries no multi-replica info (e.g. legacy
   *  single-sample conversions). Pass `undefined` to default to the single
   *  trajectory view. */
  defaultReplicas?: number[]
}) {
  const [replicas, setReplicas] = useState<number[] | undefined>(defaultReplicas)
  const [labels, setLabels] = useState<string[] | undefined>(undefined)

  useEffect(() => {
    if (!taskId) return
    let cancelled = false
    fetch(`/api/data/trajectory-status?taskId=${encodeURIComponent(taskId)}`)
      .then(r => (r.ok ? r.json() : null))
      .then((status: TrajectoryStatus | null) => {
        if (cancelled) return
        if (!status || !Array.isArray(status.dcdSizes)) {
          // No per-replica DCD info (TIGER2 statuses / pre-upgrade caches):
          // keep the caller's default replica buttons.
          return
        }
        const count = status.dcdSizes.length
        if (count <= 1) {
          setReplicas(undefined)
          setLabels(undefined)
          return
        }
        setReplicas(Array.from({ length: count }, (_, i) => i))
        const names = Array.isArray(status.samples) && status.samples.length === count
          ? status.samples.map(shortLabel)
          : undefined
        setLabels(names)
      })
      .catch(() => { /* keep default replicas */ })
    return () => { cancelled = true }
  }, [taskId])

  return (
    <div>
      <MolecularViewer taskId={taskId} replica={0} replicas={replicas} replicaLabels={labels} />
    </div>
  )
}
