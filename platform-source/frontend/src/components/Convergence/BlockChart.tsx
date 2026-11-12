import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts"
import type { ReplicaConvergence } from "./types"
import { COLOR } from "../../colors"

const E2E_COLOR = COLOR.e2e
const RG_COLOR = COLOR.rg

interface Point {
  cycle: number
  e2e: number | null
  rg: number | null
}

interface AxisSpec {
  domain: [number, number]
  ticks: number[]
}

interface ReplicaDualChartProps {
  points: Point[]
  e2eAxis: AxisSpec
  rgAxis: AxisSpec
}

function makeAxis(values: number[], step: number): AxisSpec {
  if (values.length === 0) return { domain: [0, 1], ticks: [0] }
  let lo = Math.min(...values)
  let hi = Math.max(...values)
  if (hi - lo < step) { lo -= step; hi += step }
  const start = Math.floor(lo / step)
  const end = Math.ceil(hi / step)
  const ticks: number[] = []
  for (let i = start; i <= end; i++) {
    ticks.push(Math.round(i * step * 100) / 100)
  }
  return { domain: [ticks[0], ticks[ticks.length - 1]], ticks }
}

function ReplicaDualChart({ points, e2eAxis, rgAxis }: ReplicaDualChartProps) {
  if (!points || points.length === 0) {
    return (
      <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, color: "var(--body-muted)" }}>
        No cycle data yet
      </div>
    )
  }

  const cycles = points.map(p => p.cycle)
  const minCycle = Math.min(...cycles)
  const maxCycle = Math.max(...cycles)
  const cycleStep = 25
  const cycleTicks: number[] = []
  for (let c = Math.ceil(minCycle / cycleStep) * cycleStep; c <= maxCycle; c += cycleStep) cycleTicks.push(c)
  if (cycleTicks.length === 0) cycleTicks.push(minCycle)

  return (
    <>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis
            dataKey="cycle"
            tick={{ fontSize: 11 }}
            label={{ value: "Cycle", position: "bottom", style: { fontSize: 11 } }}
            ticks={cycleTicks}
            interval={0}
          />
          <YAxis
            yAxisId="e2e"
            orientation="left"
            domain={e2eAxis.domain}
            ticks={e2eAxis.ticks}
            interval={0}
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => String(v)}
            label={{ value: "E2E (nm)", angle: -90, position: "insideLeft", style: { fontSize: 11 } }}
          />
          <YAxis
            yAxisId="rg"
            orientation="right"
            domain={rgAxis.domain}
            ticks={rgAxis.ticks}
            interval={0}
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => Number(v).toFixed(1)}
            label={{ value: "Rg (nm)", angle: 90, position: "insideRight", style: { fontSize: 11 } }}
          />
          <Tooltip formatter={(val: number, name: string) => [Number(val).toFixed(3), name]} labelFormatter={(label) => `Cycle ${label}`} />
          <Line yAxisId="e2e" type="monotone" dataKey="e2e" name="E2E (nm)" stroke={E2E_COLOR} dot={false} strokeWidth={2} isAnimationActive={false} />
          <Line yAxisId="rg" type="monotone" dataKey="rg" name="Rg (nm)" stroke={RG_COLOR} dot={false} strokeWidth={2} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </>
  )
}

export function BlockLegend() {
  return (
    <div className="legend">
      <div className="legend-item">
        <div className="legend-dot" style={{ background: E2E_COLOR }} />
        E2E (nm)
      </div>
      <div className="legend-item">
        <div className="legend-dot" style={{ background: RG_COLOR }} />
        Rg (nm)
      </div>
    </div>
  )
}

export function BlockGrid({ replicas }: { replicas?: Record<string, ReplicaConvergence> }) {
  const repsData = replicas ?? {}
  const repKeys = Object.keys(repsData).map(Number).sort((a, b) => a - b)
  if (repKeys.length === 0) {
    return <div style={{ textAlign: "center", color: "var(--body-muted)", fontSize: 13, padding: 24 }}>No replica cycle data available.</div>
  }

  let windowCycles = 0
  let firstCycle = Infinity
  let lastCycle = -Infinity
  const allE2e: number[] = []
  const allRg: number[] = []
  for (const key of repKeys) {
    const cycles = repsData[String(key)].metrics?.e2e?.recent_cycles || []
    if (cycles.length === 0) continue
    windowCycles = Math.max(windowCycles, cycles.length)
    firstCycle = Math.min(firstCycle, cycles[0].cycle)
    lastCycle = Math.max(lastCycle, cycles[cycles.length - 1].cycle)
    for (const p of cycles) if (p.value != null) allE2e.push(p.value)
    for (const p of repsData[String(key)].metrics?.rg?.recent_cycles || []) if (p.value != null) allRg.push(p.value)
  }
  if (firstCycle === Infinity) { firstCycle = 0; lastCycle = 0 }

  const e2eAxis = makeAxis(allE2e, 1)
  const rgAxis = makeAxis(allRg, 0.2)

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {repKeys.map(rep => {
          const r = repsData[String(rep)]
          const e2e = r.metrics?.e2e?.recent_cycles || []
          const rg = r.metrics?.rg?.recent_cycles || []
          const points: Point[] = e2e.map((p, i) => ({
            cycle: p.cycle,
            e2e: p.value,
            rg: rg[i]?.value ?? null,
          }))
          return (
            <div key={rep} className="chart-container" style={{ height: 280 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: "var(--body-muted)" }}>
                Replica {rep}
              </div>
              <ReplicaDualChart points={points} e2eAxis={e2eAxis} rgAxis={rgAxis} />
            </div>
          )
        })}
      </div>
      <div style={{ marginTop: 8, fontSize: 12, color: "var(--body-muted)", textAlign: "center" }}>
        Last {windowCycles} cycles ({firstCycle}–{lastCycle})
      </div>
    </div>
  )
}
