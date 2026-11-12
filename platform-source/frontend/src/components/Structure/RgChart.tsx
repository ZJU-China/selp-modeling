import type { StructureData } from "./types"
import { ReplicaGrid } from "./ReplicaGrid"
import { parseReplicaSeries } from "./parseDat"

export function RgChart({ data, stepsPerCycle = 15000 }: { data: StructureData; stepsPerCycle?: number }) {
  const points = parseReplicaSeries(data.rg ?? "", stepsPerCycle)
  if (points.length === 0) {
    return (
      <div>
        <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
          <h3 className="section-title">Radius of Gyration (Rg)</h3>
        </div>
        <div className="chart-container" style={{ height: 320, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ fontSize: 13, color: "var(--body-muted)" }}>Preview data unavailable</div>
        </div>
      </div>
    )
  }

  const max = Math.max(...points.map(p => p.value))
  const yDomain: [number, number] = [0, Math.ceil(max / 10) * 10]

  return (
    <div>
      <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
        <h3 className="section-title">Radius of Gyration (Rg)</h3>
      </div>
      <ReplicaGrid raw={data.rg!} yDomain={yDomain} yLabel="Rg (Å)" valueKey="rg" stepsPerCycle={stepsPerCycle} />
    </div>
  )
}