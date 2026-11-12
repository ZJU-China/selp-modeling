import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts"
import { COLOR, REPLICAS_COLORS } from "../../colors"
import type { StructureData } from "./types"
import { datRows, cycleTicks } from "./parseDat"

interface EnergyPoint { cycle: number; energy?: number; temp?: number }

/** Parse `# replica step total_energy(kJ/mol) temperature(K)` (either column
 *  may be empty when the term is missing from the EDR). */
function parseEnergy(raw: string, stepsPerCycle: number): Map<number, EnergyPoint[]> {
  const byRep = new Map<number, EnergyPoint[]>()
  for (const parts of datRows(raw)) {
    const rep = Number(parts[0])
    const step = Number(parts[1])
    if (isNaN(rep) || isNaN(step) || step <= 0) continue
    const energy = Number(parts[2])
    const temp = parts[3] !== undefined && parts[3] !== "" ? Number(parts[3]) : undefined
    const arr = byRep.get(rep) ?? []
    arr.push({
      cycle: Math.round(step / stepsPerCycle),
      energy: isNaN(energy) ? undefined : energy,
      temp: temp !== undefined && isNaN(temp) ? undefined : temp,
    })
    byRep.set(rep, arr)
  }
  return byRep
}

function EnergyPanel({ data, color }: { data: EnergyPoint[]; color: string }) {
  const xTicks = cycleTicks(data.map(d => d.cycle))
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="cycle" ticks={xTicks} tick={{ fontSize: 11 }} label={{ value: "Cycle", position: "bottom", style: { fontSize: 11 } }} />
        <YAxis yAxisId="energy" tick={{ fontSize: 11 }} label={{ value: "Energy (kJ/mol)", angle: -90, position: "insideLeft", style: { fontSize: 11 } }} />
        <YAxis yAxisId="temp" orientation="right" tick={{ fontSize: 11 }} />
        <Tooltip formatter={(val: number, name: string) => [val?.toFixed(1) ?? "—", name === "energy" ? "Total Energy (kJ/mol)" : "Temperature (K)"]} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line yAxisId="energy" type="monotone" dataKey="energy" stroke={color} dot={false} strokeWidth={1.5} name="Total Energy" isAnimationActive={false} />
        <Line yAxisId="temp" type="monotone" dataKey="temp" stroke={COLOR.warning} dot={false} strokeWidth={1.5} name="Temperature" isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

export function EnergyChart({ data, stepsPerCycle = 15000 }: { data: StructureData; stepsPerCycle?: number }) {
  const byRep = parseEnergy(data.energy ?? "", stepsPerCycle)
  const reps = [...byRep.keys()].sort((a, b) => a - b)
  const colors = REPLICAS_COLORS(Math.max(reps.length, 1))

  return (
    <div>
      <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
        <h3 className="section-title">Energy and Temperature</h3>
        <p className="section-desc" style={{ margin: "4px 0 0", fontSize: 13, color: "var(--body-muted)" }}>
          Per-sample total energy (kJ/mol) and temperature (K) from relax.edr, mapped onto the MD step axis.
        </p>
      </div>
      {reps.length === 0 ? (
        <div className="chart-container" style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ fontSize: 13, color: "var(--body-muted)" }}>No energy data available.</div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12 }}>
          {reps.map((rep, i) => (
            <div key={rep} className="chart-container" style={{ height: 280 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: "var(--body-muted)" }}>
                Replica {rep}
              </div>
              <EnergyPanel data={byRep.get(rep) ?? []} color={colors[i % colors.length]} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}