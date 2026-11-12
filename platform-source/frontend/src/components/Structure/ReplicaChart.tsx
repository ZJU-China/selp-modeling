import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts"
import { parseReplicaSeries, cycleTicks } from "./parseDat"

interface ReplicaChartProps {
  raw: string
  yDomain: [number, number]
  yLabel: string
  valueKey: string
  color: string
  replica?: number
  stepsPerCycle?: number
  yTicks?: number[]
}

export function ReplicaChart({ raw, yDomain, yLabel, valueKey, color, replica, stepsPerCycle = 15000, yTicks }: ReplicaChartProps) {
  const points = parseReplicaSeries(raw, stepsPerCycle)
    .filter(p => replica === undefined || p.replica === replica)
  if (points.length === 0) return null

  const data = points.map(p => ({ cycle: p.cycle, [valueKey]: p.value }))
  const xTicks = cycleTicks(data.map(d => d.cycle))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="cycle" ticks={xTicks} tick={{ fontSize: 11 }} label={{ value: "Cycle", position: "bottom", style: { fontSize: 11 } }} />
        <YAxis domain={yDomain} ticks={yTicks} tick={{ fontSize: 11 }} label={{ value: yLabel, angle: -90, position: "insideLeft", style: { fontSize: 11 } }} />
        <Tooltip formatter={(val: number) => [`${val.toFixed(2)} ${yLabel}`, valueKey]} />
        <Line type="monotone" dataKey={valueKey} stroke={color} dot={false} strokeWidth={1.5} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}