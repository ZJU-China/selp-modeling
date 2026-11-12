import { useEffect, useState } from "react"
import { MolecularViewer } from "./MolecularViewer"
import { VideoDownloadButtons } from "./VideoDownloadButtons"
import { REPLICAS_COLORS, COLOR } from "../colors"
import type { ConvergenceData } from "./Convergence/types"

interface TrajectorySectionProps {
  taskId: string
  /** Window of recent cycles to load (defaults to the task's recent_window). */
  recentWindow?: number
  /** Replica indices to offer (defaults to the task's replicas). */
  replicas?: number[]
  /** When true, this task only ever has one trajectory (e.g. a GROMACS CG
   *  task always converts a single sample's DCD, regardless of how many
   *  samples it ran) — skips the replica lookup/switcher entirely and just
   *  shows that one trajectory. */
  singleReplica?: boolean
}

/** "Last N Cycles · Molecular Dynamics Trajectory" section: a tail-window
 *  trajectory viewer with per-replica switching. Used at the top of both the
 *  Convergence page and the Dashboard. */
export function TrajectorySection({ taskId, recentWindow, replicas, singleReplica }: TrajectorySectionProps) {
  const [trajReplica, setTrajReplica] = useState(0)
  const [meta, setMeta] = useState<{ recentWindow: number; replicas: number[] }>(() =>
    singleReplica ? { recentWindow: recentWindow ?? 100, replicas: [0] }
      : recentWindow != null && replicas ? { recentWindow, replicas } : { recentWindow: 100, replicas: [0] }
  )

  const replicasKey = replicas ? replicas.join(",") : undefined

  useEffect(() => {
    if (singleReplica) {
      setMeta({ recentWindow: recentWindow ?? 100, replicas: [0] })
      return
    }
    if (recentWindow != null && replicas) {
      setMeta({ recentWindow, replicas })
      return
    }
    let cancelled = false
    fetch(`/api/data/convergence?taskId=${taskId}`)
      .then(r => r.json())
      .then((d: ConvergenceData) => {
        if (cancelled) return
        const reps = Object.keys(d.replicas ?? {}).map(Number).sort((a, b) => a - b)
        setMeta({ recentWindow: d.cycles?.recent_window ?? 100, replicas: reps.length ? reps : [0] })
      })
      .catch(() => { if (!cancelled) setMeta({ recentWindow: 100, replicas: [0] }) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId, recentWindow, replicasKey, singleReplica])

  const { recentWindow: windowCount, replicas: reps } = meta
  const activeReplica = reps.includes(trajReplica) ? trajReplica : reps[0]
  const replicaColors = REPLICAS_COLORS(reps.length)

  return (
    <div className="section">
      <div className="section-header">
        <h3 className="section-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
          Last {windowCount} Cycles · Molecular Dynamics Trajectory
        </h3>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {!singleReplica && (
            <>
              <span style={{ fontSize: 13, color: COLOR.muted, marginRight: 4 }}>Replica:</span>
              {reps.map(rep => (
                <button
                  key={rep}
                  onClick={() => setTrajReplica(rep)}
                  style={{
                    padding: "6px 14px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600,
                    cursor: "pointer", transition: "all 0.15s",
                    background: activeReplica === rep ? replicaColors[rep] : "transparent",
                    color: activeReplica === rep ? "white" : replicaColors[rep],
                    outline: activeReplica === rep ? "none" : `1px solid ${replicaColors[rep]}`,
                  }}
                >
                  Replica {rep}
                </button>
              ))}
            </>
          )}
          <VideoDownloadButtons taskId={taskId} replica={activeReplica} />
        </div>
      </div>
      <MolecularViewer taskId={taskId} replica={activeReplica} height={420} lastCycles={windowCount} zoomRatio={1 / 1.618} hideHeader />
    </div>
  )
}
