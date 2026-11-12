import { ReplicaChart } from "./ReplicaChart"
import { REPLICAS_COLORS } from "../../colors"
import { replicaIds } from "./parseDat"

interface ReplicaGridProps {
  raw: string
  yDomain: [number, number]
  yLabel: string
  valueKey: string
  stepsPerCycle?: number
  yTicks?: number[]
  replicas?: number[]
}

const DEFAULT_REPLICAS = [0, 1, 2, 3]

/** One line chart per replica. Replica ids come from the raw file (falls back
 *  to the TIGER2 4-replica ladder when nothing parses yet). Column layout
 *  auto-fits the available replica count. */
export function ReplicaGrid({ raw, yDomain, yLabel, valueKey, stepsPerCycle, yTicks, replicas }: ReplicaGridProps) {
  const ids = replicas && replicas.length > 0 ? replicas : replicaIds(raw)
  const list = ids.length > 0 ? ids : DEFAULT_REPLICAS
  const colors = REPLICAS_COLORS(list.length)
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 12 }}>
      {list.map((rep, i) => (
        <div key={rep} className="chart-container" style={{ height: 260 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4, color: "var(--body-muted)" }}>
            Replica {rep}
          </div>
          <ReplicaChart raw={raw} yDomain={yDomain} yTicks={yTicks} yLabel={yLabel} valueKey={valueKey} color={colors[i % colors.length]} replica={rep} stepsPerCycle={stepsPerCycle} />
        </div>
      ))}
    </div>
  )
}