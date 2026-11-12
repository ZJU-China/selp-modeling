import { useState } from "react"
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Label } from "recharts"
import { REPLICAS_COLORS } from "../../colors"

export interface TemperatureTraceReplicas {
  id: number
  temp_avg?: number
  temp_trace: { step: number; temp: number }[]
}

export interface TemperatureTraceConfig {
  steps_per_cycle: number
  target_temps?: number[]
  temp_range?: number[]
}

export interface TemperatureTraceProps {
  replicas: Record<string, TemperatureTraceReplicas>
  config: TemperatureTraceConfig
  animate: boolean
  title?: string
  selectable?: boolean
  yDomain?: [number, number]
}

export function TemperatureTrace({ replicas, config, animate, title, selectable, yDomain }: TemperatureTraceProps) {
  const [selectedReplica, setSelectedReplica] = useState<number | null>(null)
  const spc = config.steps_per_cycle

  const allSteps = new Set<number>()
  Object.values(replicas).forEach(r => r.temp_trace.forEach(t => allSteps.add(t.step)))
  const chartData = Array.from(allSteps).sort((a, b) => a - b).map(step => {
    const point: Record<string, number> = { cycle: step / spc }
    Object.values(replicas).forEach(r => {
      const match = r.temp_trace.find(t => t.step === step)
      if (match) point[`replica${r.id}`] = match.temp
    })
    return point
  })

  const yMin = yDomain?.[0] ?? (config.temp_range?.[0] ?? 250) - 10
  const replicaColors = REPLICAS_COLORS(Object.keys(replicas).length)

  return (
    <div className="section">
      <div className="section-header">
        <h3 className="section-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/>
          </svg>
          {title || "Temperature Trace"}
        </h3>
        <div className="legend">
          {Object.values(replicas).map(r => (
            <div key={r.id} className="legend-item"
              style={selectable ? { cursor: "pointer" } : undefined}
              onClick={selectable ? () => setSelectedReplica(selectedReplica === r.id ? null : r.id) : undefined}>
              <div className="legend-dot" style={{ background: replicaColors[r.id] }}></div>
              {config.target_temps
                ? `Replica ${r.id} (target ${config.target_temps[r.id]}K)`
                : `Rep ${r.id} (${r.temp_avg}K avg)`
              }
            </div>
          ))}
        </div>
      </div>
      <div className="chart-container" style={{ height: 340 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 10, right: 20, left: 60, bottom: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
            <XAxis dataKey="cycle" tick={{ fontSize: 12 }} tickFormatter={v => Number.isInteger(v) ? `${v}` : `${v.toFixed(0)}`}>
              <Label value="Cycle" offset={-18} position="insideBottom" style={{ fontSize: 13, fill: "var(--chart-text)" }} />
            </XAxis>
            <YAxis domain={[yMin, 440]} tick={{ fontSize: 12 }}>
              <Label value="Temperature (K)" angle={-90} position="insideLeft" offset={0} style={{ fontSize: 13, textAnchor: "middle", fill: "var(--chart-text)" }} />
            </YAxis>
            <Tooltip
              formatter={(value: number, name: string) => [`${value.toFixed(1)} K`, name]}
              labelFormatter={v => `Cycle ${Math.round(v)}`}
            />
            {Object.values(replicas).map(r => (
              <Line key={r.id} type="monotone" dataKey={`replica${r.id}`} stroke={replicaColors[r.id]} dot={false}
                strokeWidth={selectable && selectedReplica !== null && selectedReplica !== r.id ? 0.5 : 2}
                opacity={selectable && selectedReplica !== null && selectedReplica !== r.id ? 0.3 : 1}
                isAnimationActive={animate} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
