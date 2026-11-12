import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts"
import type { StructureData } from "./types"
import { REPLICAS_COLORS, COLOR } from "../../colors"

const STEPS_PER_CYCLE = 15000

function parseReplicaSS(raw: string): { replica: number; cycle: number; helix: number; sheet: number; coil: number }[] {
  if (!raw) return []
  const lines = raw.trim().split("\n").filter(l => l.trim() && !l.startsWith("#"))
  const result: { replica: number; cycle: number; helix: number; sheet: number; coil: number }[] = []
  for (const line of lines) {
    const parts = line.trim().split(/[\s,\t]+/)
    const rep = Number(parts[0])
    if (isNaN(rep)) continue
    const step = Number(parts[1]) || 0
    if (step <= 0) continue
    result.push({
      replica: rep,
      cycle: Math.round(step / STEPS_PER_CYCLE),
      helix: Number(parts[2]) || 0,
      sheet: Number(parts[3]) || 0,
      coil: Number(parts[4]) || 0,
    })
  }
  return result
}

export function SsChart({ data }: { data: StructureData }) {
  const allData = parseReplicaSS(data.ss ?? "")
  const useMock = allData.length === 0

  if (useMock) {
    return (
      <div>
        <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
          <h3 className="section-title">Secondary Structure Content</h3>
        </div>
        <div style={{ padding: 48, textAlign: "center", color: "var(--body-muted)" }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>&#128269;</div>
          <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 4 }}>No secondary structure data available</div>
          <div style={{ fontSize: 13 }}>Run DSSP analysis on the server to generate secondary structure assignments</div>
        </div>
      </div>
    )
  }

  const maxCycle = Math.max(...allData.map(d => d.cycle))
  const xTicks = Array.from({ length: Math.floor(maxCycle / 100) + 2 }, (_, i) => i * 100)

  return (
    <div>
      <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
        <h3 className="section-title">Secondary Structure Content</h3>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        {[0, 1, 2, 3].map(rep => {
          const repData = allData.filter(d => d.replica === rep)
          const color = REPLICAS_COLORS(4)[rep] ?? COLOR.mutedAlt
          return (
            <div key={rep} className="chart-container" style={{ height: 260 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: "var(--body-muted)" }}>
                Replica {rep}
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={repData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                  <XAxis dataKey="cycle" ticks={xTicks} tick={{ fontSize: 11 }} label={{ value: "Cycle", position: "bottom", style: { fontSize: 11 } }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} label={{ value: "%", angle: -90, position: "insideLeft", style: { fontSize: 11 } }} />
                  <Tooltip formatter={(value: number, name: string) => [`${value.toFixed(1)}%`, name]} />
                  <Area type="monotone" dataKey="helix" stackId="1" stroke={COLOR.danger} fill={`${color}20`} name="α-Helix" isAnimationActive={false} />
                  <Area type="monotone" dataKey="sheet" stackId="1" stroke={COLOR.accent} fill={`${color}20`} name="β-Sheet" isAnimationActive={false} />
                  <Area type="monotone" dataKey="coil" stackId="1" stroke={COLOR.mutedAlt} fill={`${color}20`} name="Coil" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )
        })}
      </div>
    </div>
  )
}
