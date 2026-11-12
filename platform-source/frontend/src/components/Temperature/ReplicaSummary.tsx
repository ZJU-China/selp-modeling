import { REPLICAS_COLORS } from "../../colors"

interface SimData {
  config: {
    target_temps: number[]
  }
  replicas: Record<string, {
    id: number
    temp_avg: number
    temp_min: number
    temp_max: number
    exchange_count: number
  }>
}

export function ReplicaSummary({ data }: { data: SimData }) {
  const { replicas, config } = data
  const colors = REPLICAS_COLORS(Object.keys(replicas).length)

  return (
    <div className="section">
      <div className="section-header">
        <h3 className="section-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          Replica Temperature Summary
        </h3>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th>Replica</th>
            <th>Target Temp</th>
            <th>Avg Temp</th>
            <th>Min Temp</th>
            <th>Max Temp</th>
            <th>Exchanges</th>
          </tr>
        </thead>
        <tbody>
          {Object.values(replicas).map(r => (
            <tr key={r.id}>
              <td><span style={{ color: colors[r.id], fontWeight: 600 }}>●</span> Replica {r.id}</td>
              <td>{config.target_temps[r.id]} K</td>
              <td>{r.temp_avg} K</td>
              <td>{r.temp_min} K</td>
              <td>{r.temp_max} K</td>
              <td>{r.exchange_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
