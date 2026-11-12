import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts"
import { COLOR, REPLICAS_COLORS } from "../../colors"
import type { StructureData } from "./types"
import { datRows, cycleTicks } from "./parseDat"

interface ChainRgPoint { cycle: number; mean?: number; min?: number; max?: number }

/** Parse `# replica step mean_rg(A) min_rg(A) max_rg(A)` per replica. */
function parseChainRg(raw: string, stepsPerCycle: number): Map<number, ChainRgPoint[]> {
  const byRep = new Map<number, ChainRgPoint[]>()
  for (const parts of datRows(raw)) {
    const rep = Number(parts[0])
    const step = Number(parts[1])
    if (isNaN(rep) || isNaN(step) || step <= 0) continue
    const num = (s?: string) => {
      const v = s !== undefined && s !== "" ? Number(s) : undefined
      return v !== undefined && isNaN(v) ? undefined : v
    }
    const arr = byRep.get(rep) ?? []
    arr.push({ cycle: Math.round(step / stepsPerCycle), mean: num(parts[2]), min: num(parts[3]), max: num(parts[4]) })
    byRep.set(rep, arr)
  }
  return byRep
}

function NetworkPanel({ data, color }: { data: ChainRgPoint[]; color: string }) {
  const xTicks = cycleTicks(data.map(d => d.cycle))
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="cycle" ticks={xTicks} tick={{ fontSize: 11 }} label={{ value: "Cycle", position: "bottom", style: { fontSize: 11 } }} />
        <YAxis tick={{ fontSize: 11 }} label={{ value: "Rg (Å)", angle: -90, position: "insideLeft", style: { fontSize: 11 } }} />
        <Tooltip formatter={(val: number, name: string) => [val?.toFixed(2) ?? "—", name]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="mean" stroke={color} dot={false} strokeWidth={1.5} name="Mean" isAnimationActive={false} />
        <Line type="monotone" dataKey="min" stroke={COLOR.muted} strokeDasharray="4 4" dot={false} strokeWidth={1.2} name="Min" isAnimationActive={false} />
        <Line type="monotone" dataKey="max" stroke={COLOR.muted} strokeDasharray="4 4" dot={false} strokeWidth={1.2} name="Max" isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function NetworkChart({ data, stepsPerCycle = 15000 }: { data: StructureData; stepsPerCycle?: number }) {
  const byRep = parseChainRg(data.chainRg ?? "", stepsPerCycle)
  const reps = [...byRep.keys()].sort((a, b) => a - b)
  const colors = REPLICAS_COLORS(Math.max(reps.length, 1))

  return (
    <div>
      <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
        <h3 className="section-title">Per-chain Radius of Gyration</h3>
        <p className="section-desc" style={{ margin: "4px 0 0", fontSize: 13, color: "var(--body-muted)" }}>
          Mean / min / max radius of gyration across the 32 network chains (Å), per sample.
        </p>
      </div>
      {reps.length === 0 ? (
        <div className="chart-container" style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ fontSize: 13, color: "var(--body-muted)" }}>No network data available.</div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12 }}>
          {reps.map((rep, i) => (
            <div key={rep} className="chart-container" style={{ height: 280 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: "var(--body-muted)" }}>
                Replica {rep}
              </div>
              <NetworkPanel data={byRep.get(rep) ?? []} color={colors[i % colors.length]} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}