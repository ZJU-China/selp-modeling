import { Fragment, useState, useEffect } from "react"
import { ConvergenceSummary } from "./ConvergenceSummary"
import { BlockGrid, BlockLegend } from "./BlockChart"
import { ReplicaDetails } from "./ReplicaDetails"
import { TrajectorySection } from "../TrajectorySection"
import { COLOR } from "../../colors"
import { METRIC_META, type ConvergenceData, type MetricKey } from "./types"

export type { ConvergenceData }
export { BlockGrid } from "./BlockChart"
export { ConvergenceSummary } from "./ConvergenceSummary"
export { ReplicaDetails } from "./ReplicaDetails"

const POLL_INTERVAL_MS = 600_000

export function ConvergencePage({ selectedTask, detectOnly = false }: { selectedTask: { id: string; name: string; taskType?: string } | null; detectOnly?: boolean }) {
  const [data, setData] = useState<ConvergenceData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!selectedTask) return
    setLoading(true)
    setError(null)

    const load = () => {
      fetch(`/api/data/convergence?taskId=${selectedTask.id}${detectOnly ? "&detectOnly=1" : ""}`)
        .then(r => r.json())
        .then(d => { setData(d); setLoading(false) })
        .catch(e => { setError(e.message); setLoading(false) })
    }
    load()
    const id = setInterval(load, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [selectedTask?.id, detectOnly])

  if (!selectedTask) return <div className="container" style={{ padding: 48 }}><div className="empty-state">Select a task in the header to view convergence.</div></div>

  if (loading) return <div className="container loading" style={{ padding: 48 }}>Checking convergence (reads cached trajectories)...</div>
  if (error) return <div className="container" style={{ padding: 48 }}><div className="empty-state">Error: {error}</div></div>
  if (!data) return <div className="container" style={{ padding: 48 }}><div className="empty-state">No convergence data available. Run trajectory sync first.</div></div>
  if (data.error) return <div className="container" style={{ padding: 48 }}><div className="empty-state">{data.error}</div></div>

  const metricKeys = (Object.keys(METRIC_META) as MetricKey[]).filter(k => data.thresholds?.metrics?.[k] != null)
  const replicaKeys = data.replicas ? Object.keys(data.replicas).map(Number).sort((a, b) => a - b) : []
  const recentWindow = data.cycles?.recent_window ?? 100

  if (metricKeys.length === 0 || replicaKeys.length === 0) {
    return (
      <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>
        <div className="hero" style={{ textAlign: "center" }}>
          <h1>Convergence Detection</h1>
          <p className="hero-subtitle" style={{ margin: "0 auto" }}>{selectedTask.name}</p>
        </div>
        <div className="empty-state" style={{ padding: 48 }}>
          Convergence analysis is not applicable to this task type.
        </div>
      </div>
    )
  }

  return (
    <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>
      <div className="hero" style={{ textAlign: "center" }}>
        <h1>Convergence Detection</h1>
        <p className="hero-subtitle" style={{ margin: "0 auto" }}>
          {selectedTask.name} · E2E + Rg block stability across {Object.keys(data.replicas).length} replicas · Updated {new Date().toLocaleString()}
        </p>
      </div>

      {data.stopped && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          padding: "12px 16px", marginBottom: 16, borderRadius: 8,
          background: COLOR.infoSoft, border: `1px solid ${COLOR.infoSoftBorder}`, color: COLOR.infoSoftFg,
          fontSize: 14, fontWeight: 600,
        }}>
          ⏹ Simulation stopped — converged on both E2E and Rg
        </div>
      )}

      {data.converged && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          padding: "12px 16px", marginBottom: 16, borderRadius: 8,
          background: COLOR.successSoft, border: `1px solid ${COLOR.successSoftBorder}`, color: COLOR.successSoftFg,
          fontSize: 14, fontWeight: 600,
        }}>
          ✓ Simulation has converged — E2E and Rg stable for {data.stable_checks} consecutive checks
        </div>
      )}

      <TrajectorySection taskId={selectedTask.id} recentWindow={recentWindow} replicas={replicaKeys} singleReplica={selectedTask.taskType === "gromacs_cg"} />

      <ConvergenceSummary data={data} />

      <div className="section">
        <div className="section-header">
          <h3 className="section-title">Convergence Criteria</h3>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Criterion</th>
              <th>Threshold</th>
              {replicaKeys.map(rep => <th key={rep}>Replica {rep}</th>)}
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {metricKeys.map(key => {
              const th = data.thresholds.metrics[key]
              const overall = data.metrics?.[key]
              const status = overall?.all_converged ? (
                <span className="badge badge-success">All replicas pass</span>
              ) : (
                <span className="badge badge-warning">{overall?.converged_replicas ?? 0}/{replicaKeys.length} replicas pass</span>
              )
              const cell = (rep: number, v: number | null, limit: number) => {
                if (v == null) {
                  return <td key={rep} style={{ color: "var(--body-muted)" }}>–</td>
                }
                const ok = v < limit
                return (
                  <td key={rep} style={{ color: ok ? COLOR.successSoftFg : COLOR.fail, fontWeight: ok ? 400 : 600 }}>
                    {v.toFixed(3)} {ok ? "✓" : "✗"}
                  </td>
                )
              }
              return (
                <Fragment key={key}>
                  <tr>
                    <td rowSpan={2}><strong>{METRIC_META[key].label}</strong> ({th.unit})</td>
                    <td>Mean drift (|Δmean|)</td>
                    <td>&lt; {th.mean_diff} {th.unit}</td>
                    {replicaKeys.map(rep => cell(rep, data.replicas[String(rep)]?.metrics?.[key]?.details?.mean_diff ?? null, th.mean_diff))}
                    <td rowSpan={2}>{status}</td>
                  </tr>
                  <tr>
                    <td>Std ratio</td>
                    <td>&lt; {th.std_ratio}×</td>
                    {replicaKeys.map(rep => cell(rep, data.replicas[String(rep)]?.metrics?.[key]?.details?.std_ratio ?? null, th.std_ratio))}
                  </tr>
                </Fragment>
              )
            })}
            <tr>
              <td colSpan={4 + replicaKeys.length}>
                <strong>Stability</strong> — &gt;= {data.required_checks} consecutive checks on all replicas, both metrics ({data.stable_checks}/{data.required_checks})
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="section">
        <div className="section-header">
          <h3 className="section-title">Recent {recentWindow} Cycles · E2E + Rg</h3>
          <BlockLegend />
        </div>
        <BlockGrid replicas={data.replicas} />
      </div>

      <ReplicaDetails data={data} />
    </div>
  )
}
