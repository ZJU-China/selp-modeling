import { useState, useEffect, useRef } from "react"
import { TemperatureTrace } from "./TemperatureTrace"
import { VisitExchange } from "./VisitExchange"
import { ReplicaSummary } from "./ReplicaSummary"
import { ScheduleConfig } from "./ScheduleConfig"
import type { TempData } from "./types"
import { REPLICAS_COLORS } from "../../colors"

interface SectionDef {
  id: string
  component: React.ComponentType<any>
  getProps: (d: TempData, animate: boolean) => Record<string, unknown>
}

const SECTIONS: SectionDef[] = [
  { id: "trace", component: TemperatureTrace, getProps: (d, a) => ({ data: d, animate: a }) },
  { id: "visit-exchange", component: VisitExchange, getProps: (d, a) => ({ data: d, animate: a }) },
  { id: "summary", component: ReplicaSummary, getProps: (d) => ({ data: d }) },
  { id: "schedule", component: ScheduleConfig, getProps: (d) => ({ config: d.config }) },
]

export function TemperaturePage({ selectedTask }: { selectedTask: { id: string; name: string } | null }) {
  const [data, setData] = useState<TempData | null>(null)
  const [animate, setAnimate] = useState(false)
  const firstLoad = useRef(true)

  useEffect(() => {
    if (!selectedTask) return
    const load = () => {
      fetch(`/api/data/sim-status?taskId=${selectedTask.id}`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
        .then(d => { setData(d); setAnimate(firstLoad.current); firstLoad.current = false })
        .catch(() => {})
    }
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
  }, [selectedTask?.id])

  if (!selectedTask) return <div className="container" style={{ padding: 48 }}><div className="empty-state">Select a task in the header.</div></div>
  if (!data) return <div className="container loading" style={{ padding: 48 }}>Loading...</div>

  const { replicas, config } = data
  const colors = REPLICAS_COLORS(Object.keys(replicas).length)

  if (config.method === "GROMACS CG (Martini)") {
    return (
      <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>
        <div className="hero" style={{ textAlign: "center" }}>
          <h1>Temperature Analysis</h1>
          <p className="hero-subtitle" style={{ margin: "0 auto" }}>{selectedTask.name}</p>
        </div>
        <div className="empty-state" style={{ padding: 48 }}>
          This task runs at a fixed temperature ({config.temp_range[0]} K, no replica exchange), so temperature-exchange analysis is not applicable.
        </div>
      </div>
    )
  }

  return (
    <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>
      <div className="hero" style={{ textAlign: "center" }}>
        <h1>Temperature Analysis</h1>
        <p className="hero-subtitle" style={{ margin: "0 auto" }}>
          TIGER2 temperature-weighted replica exchange · {config.num_replicas} replicas · {config.temp_range[0]}–{config.temp_range[1]} K exponential distribution
        </p>
      </div>

      <div className="stats-panel">
        {Object.values(replicas).map(r => (
          <div key={r.id} className="stat-card">
            <div className="stat-value" style={{ fontSize: 24, color: colors[r.id] }}>
              {r.temp_avg} K
            </div>
            <div className="stat-label">Replica {r.id} Avg</div>
          </div>
        ))}
      </div>

      {SECTIONS.map(s => {
        const C = s.component
        return <C key={s.id} {...s.getProps(data, animate)} />
      })}
    </div>
  )
}
