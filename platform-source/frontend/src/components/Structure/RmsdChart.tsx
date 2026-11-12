import type { StructureData } from "./types"
import { ReplicaGrid } from "./ReplicaGrid"
import { parseReplicaSeries } from "./parseDat"

export function RmsdChart({ data, stepsPerCycle = 15000 }: { data: StructureData; stepsPerCycle?: number }) {
  const points = parseReplicaSeries(data.rmsd ?? "", stepsPerCycle)
  if (points.length === 0) {
    return (
      <div>
        <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
          <h3 className="section-title">Root Mean Square Deviation</h3>
        </div>
        <div style={{ padding: 48, textAlign: "center", color: "var(--body-muted)" }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>&#128269;</div>
          <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 4 }}>No RMSD data available</div>
          <div style={{ fontSize: 13 }}>Run structural analysis on the server to generate RMSD measurements</div>
        </div>
      </div>
    )
  }

  const maxVal = Math.max(...points.map(p => p.value))
  const yDomain: [number, number] = [0, Math.ceil(maxVal * 2) / 2]

  return (
    <div>
      <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
        <h3 className="section-title">Root Mean Square Deviation</h3>
      </div>
      <ReplicaGrid raw={data.rmsd!} yDomain={yDomain} yLabel="RMSD (Å)" valueKey="rmsd" stepsPerCycle={stepsPerCycle} />
    </div>
  )
}