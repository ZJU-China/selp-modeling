import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts"
import { COLOR, REPLICAS_COLORS } from "../../colors"
import type { StructureData } from "./types"
import { datRows, cycleTicks } from "./parseDat"

interface CrosslinkPoint { cycle: number; mean?: number; min?: number; max?: number }

interface CrosslinkLink {
  chainA: number
  siteA: number
  chainB: number
  siteB: number
  ref?: number
  mean?: number
  min?: number
  max?: number
  std?: number
}

/** Parse `# replica step mean(A) min(A) max(A)` per replica. */
function parseSeries(raw: string, stepsPerCycle: number): Map<number, CrosslinkPoint[]> {
  const byRep = new Map<number, CrosslinkPoint[]>()
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

/**
 * Parse crosslink_table.tsv. First data row is a header of the form
 * `# chain_a site_a chain_b site_b ref(A) mean(A) min(A) max(A) std(A)` and is
 * skipped by datRows; remaining columns land at fixed offsets.
 */
function parseLinks(raw: string): CrosslinkLink[] {
  const out: CrosslinkLink[] = []
  for (const parts of datRows(raw)) {
    if (parts.length < 9) continue
    const chainA = Number(parts[0])
    const siteA = Number(parts[1])
    const chainB = Number(parts[2])
    const siteB = Number(parts[3])
    if (isNaN(chainA) || isNaN(siteA) || isNaN(chainB) || isNaN(siteB)) continue
    const num = (s: string | undefined) => (s !== undefined && s !== "" && !isNaN(Number(s)) ? Number(s) : undefined)
    out.push({
      chainA, siteA, chainB, siteB,
      ref: num(parts[4]),
      mean: num(parts[5]),
      min: num(parts[6]),
      max: num(parts[7]),
      std: num(parts[8]),
    })
  }
  return out
}

function SeriesPanel({ data, color }: { data: CrosslinkPoint[]; color: string }) {
  const xTicks = cycleTicks(data.map(d => d.cycle))
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="cycle" ticks={xTicks} tick={{ fontSize: 11 }} label={{ value: "Cycle", position: "bottom", style: { fontSize: 11 } }} />
        <YAxis tick={{ fontSize: 11 }} label={{ value: "Distance (Å)", angle: -90, position: "insideLeft", style: { fontSize: 11 } }} />
        <Tooltip formatter={(val: number, name: string) => [val?.toFixed(2) ?? "—", name]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="mean" stroke={color} dot={false} strokeWidth={1.5} name="Mean" isAnimationActive={false} />
        <Line type="monotone" dataKey="min" stroke={COLOR.muted} strokeDasharray="4 4" dot={false} strokeWidth={1.2} name="Min" isAnimationActive={false} />
        <Line type="monotone" dataKey="max" stroke={COLOR.muted} strokeDasharray="4 4" dot={false} strokeWidth={1.2} name="Max" isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function CrosslinkChart({ data, stepsPerCycle = 15000 }: { data: StructureData; stepsPerCycle?: number }) {
  const byRep = parseSeries(data.crosslink ?? "", stepsPerCycle)
  const reps = [...byRep.keys()].sort((a, b) => a - b)
  const colors = REPLICAS_COLORS(Math.max(reps.length, 1))

  const links = parseLinks(data.crosslinkTable ?? "")
    .sort((a, b) => (b.max ?? 0) - (a.max ?? 0))
    .slice(0, 12)

  return (
    <div>
      <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
        <h3 className="section-title">Network Crosslink Distances</h3>
        <p className="section-desc" style={{ margin: "4px 0 0", fontSize: 13, color: "var(--body-muted)" }}>
          Mean / min / max distance (Å) across the network's crosslink pairs, per sample. Table shows the most stretched links.
        </p>
      </div>
      {reps.length === 0 ? (
        <div className="chart-container" style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ fontSize: 13, color: "var(--body-muted)" }}>No crosslink data available.</div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12, marginBottom: 4 }}>
          {reps.map((rep, i) => (
            <div key={rep} className="chart-container" style={{ height: 280 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: "var(--body-muted)" }}>
                Replica {rep}
              </div>
              <SeriesPanel data={byRep.get(rep) ?? []} color={colors[i % colors.length]} />
            </div>
          ))}
        </div>
      )}

      {links.length > 0 && (
        <>
          <div style={{ fontSize: 14, fontWeight: 600, margin: "12px 0 8px" }}>Most stretched crosslinks</div>
          <table className="data-table">
            <thead>
              <tr><th>Chain A</th><th>Site A</th><th>Chain B</th><th>Site B</th><th>Ref (Å)</th><th>Mean (Å)</th><th>Min (Å)</th><th>Max (Å)</th><th>Std (Å)</th></tr>
            </thead>
            <tbody>
              {links.map(l => {
                const stretched = l.ref !== undefined && l.max !== undefined && l.max > l.ref * 1.1
                return (
                  <tr key={`${l.chainA}-${l.siteA}-${l.chainB}-${l.siteB}`} style={stretched ? { background: "var(--danger-soft)" } : undefined}>
                    <td>{l.chainA}</td><td>{l.siteA}</td><td>{l.chainB}</td><td>{l.siteB}</td>
                    <td>{l.ref?.toFixed(1) ?? "—"}</td>
                    <td>{l.mean?.toFixed(1) ?? "—"}</td>
                    <td>{l.min?.toFixed(1) ?? "—"}</td>
                    <td style={{ color: stretched ? COLOR.danger : undefined, fontWeight: stretched ? 600 : undefined }}>{l.max?.toFixed(1) ?? "—"}</td>
                    <td>{l.std?.toFixed(1) ?? "—"}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}