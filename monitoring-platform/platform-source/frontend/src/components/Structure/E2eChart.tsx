import type { StructureData } from "./types"
import { ReplicaGrid } from "./ReplicaGrid"
import { parseReplicaSeries } from "./parseDat"

export function E2eChart({ data, stepsPerCycle = 15000 }: { data: StructureData; stepsPerCycle?: number }) {
  const points = parseReplicaSeries(data.e2e ?? "", stepsPerCycle)
  if (points.length === 0) {
    return (
      <div>
        <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
          <h3 className="section-title">End-to-End Distance</h3>
        </div>
        <div className="chart-container" style={{ height: 320, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ fontSize: 13, color: "var(--body-muted)" }}>Preview data unavailable</div>
        </div>
      </div>
    )
  }

  const maxVal = Math.max(...points.map(p => p.value))
  const yMax = Math.max(200, Math.ceil(maxVal / 50) * 50)
  const yDomain: [number, number] = [0, yMax]
  const yTicks = Array.from({ length: yMax / 50 + 1 }, (_, i) => i * 50)

  return (
    <div>
      <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
        <h3 className="section-title">End-to-End Distance</h3>
      </div>
      <ReplicaGrid raw={data.e2e!} yDomain={yDomain} yTicks={yTicks} yLabel="E2E (Å)" valueKey="e2e" stepsPerCycle={stepsPerCycle} />
    </div>
  )
}