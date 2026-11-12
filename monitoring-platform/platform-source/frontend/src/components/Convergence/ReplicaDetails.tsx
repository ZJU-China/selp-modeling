import { REPLICAS_COLORS, COLOR } from "../../colors"
import { METRIC_META, type ConvergenceData, type MetricKey } from "./types"

export function ReplicaDetails({ data }: { data: ConvergenceData }) {
  const { thresholds } = data
  const reps = Object.entries(data.replicas).sort(([a], [b]) => Number(a) - Number(b))
  const replicaColors = REPLICAS_COLORS(reps.length)
  const metricKeys = (Object.keys(METRIC_META) as MetricKey[]).filter(k => thresholds.metrics?.[k] != null)

  return (
    <div className="section">
      <div className="section-header">
        <h3 className="section-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 2a10 10 0 0 1 0 20"/>
          </svg>
          Replica Convergence Details
        </h3>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Rep</th>
              <th>Frames</th>
              {metricKeys.map(key => (
                <th key={key} colSpan={2}>
                  {METRIC_META[key].short} · Mean prev / curr
                </th>
              ))}
              {metricKeys.map(key => (
                <th key={key}>|ΔMean| {METRIC_META[key].short}</th>
              ))}
              {metricKeys.map(key => (
                <th key={key}>Std ratio {METRIC_META[key].short}</th>
              ))}
              <th>Converged</th>
            </tr>
          </thead>
          <tbody>
            {reps.map(([id, r]) => {
              const color = replicaColors[Number(id)] ?? COLOR.mutedAlt
              return (
                <tr key={id}>
                  <td><span style={{ color, fontWeight: 600 }}>●</span> {id}</td>
                  <td>{r.n_frames ?? "—"}</td>
                  {metricKeys.map(key => {
                    const m = r.metrics?.[key]
                    return [
                      <td key={`${key}-prev`} style={{ whiteSpace: "nowrap" }}>
                        {m?.details?.mean_prev != null ? m.details.mean_prev.toFixed(3) : "—"}
                      </td>,
                      <td key={`${key}-curr`} style={{ whiteSpace: "nowrap" }}>
                        {m?.details?.mean_curr != null ? m.details.mean_curr.toFixed(3) : "—"}
                      </td>,
                    ]
                  })}
                  {metricKeys.map(key => {
                    const th = thresholds.metrics[key]
                    const d = r.metrics?.[key]?.details
                    const ok = th && d && d.mean_diff != null && d.mean_diff < th.mean_diff
                    return (
                      <td key={key} style={{ color: r.error ? "var(--body-muted)" : ok ? "var(--primary)" : "var(--danger)", fontWeight: 600 }}>
                        {r.error ? "—" : d?.mean_diff != null ? d.mean_diff.toFixed(3) : "—"}
                      </td>
                    )
                  })}
                  {metricKeys.map(key => {
                    const th = thresholds.metrics[key]
                    const d = r.metrics?.[key]?.details
                    const ok = th && d && d.std_ratio != null && d.std_ratio < th.std_ratio
                    return (
                      <td key={key} style={{ color: r.error ? "var(--body-muted)" : ok ? "var(--primary)" : "var(--danger)", fontWeight: 600 }}>
                        {r.error ? "—" : d?.std_ratio != null ? d.std_ratio.toFixed(2) : "—"}
                      </td>
                    )
                  })}
                  <td>
                    {r.error ? (
                      <span className="badge badge-danger" title={r.error}>ERR</span>
                    ) : r.converged ? (
                      <span className="badge badge-success">✓ Pass</span>
                    ) : (
                      <span className="badge badge-warning">✗ Fail</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
