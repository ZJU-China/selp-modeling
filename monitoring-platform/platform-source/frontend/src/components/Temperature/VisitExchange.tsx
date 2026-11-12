import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from "recharts"
import { REPLICAS_COLORS, TEMP_COLORS, COLOR } from "../../colors"

interface SimData {
  replicas: Record<string, {
    id: number
    exchange_count: number
  }>
  temp_visit_counts: Record<string, number>
}

export function VisitExchange({ data, animate }: { data: SimData; animate: boolean }) {
  const { replicas, temp_visit_counts } = data

  const visitData = Object.entries(temp_visit_counts).map(([temp, visits]) => ({
    temp,
    visits,
    color: TEMP_COLORS[temp] ?? COLOR.info,
  }))

  const replicaColors = REPLICAS_COLORS(Object.keys(replicas).length)
  const exchangeSummary = Object.values(replicas).map(r => ({
    replica: `Rep ${r.id}`,
    exchanges: r.exchange_count,
    color: replicaColors[r.id],
  }))

  return (
    <div className="chart-row">
      <div className="section">
        <div className="section-header">
          <h3 className="section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="9" y1="3" x2="9" y2="21"/>
            </svg>
            Temperature Visit Counts
          </h3>
        </div>
        <div className="chart-container" style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={visitData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="temp" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="visits" radius={[6, 6, 0, 0]} isAnimationActive={animate}>
                {visitData.map((entry, index) => (
                  <Cell key={index} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="section">
        <div className="section-header">
          <h3 className="section-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="17 1 21 5 17 9"/>
              <path d="M3 11V9a4 4 0 0 1 4-4h14"/>
              <polyline points="7 23 3 19 7 15"/>
              <path d="M21 13v2a4 4 0 0 1-4 4H3"/>
            </svg>
            Exchanges per Replica
          </h3>
        </div>
        <div className="chart-container" style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={exchangeSummary}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="replica" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Bar dataKey="exchanges" radius={[6, 6, 0, 0]} isAnimationActive={animate}>
                {exchangeSummary.map((entry, index) => (
                  <Cell key={index} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}
