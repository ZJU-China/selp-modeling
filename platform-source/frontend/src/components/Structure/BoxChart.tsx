import { COLOR } from "../../colors"
import type { StructureData } from "./types"
import { datRows } from "./parseDat"

interface BoxRow { replica: number; x: number; y: number; z: number }

/** Parse `# replica step box_x(nm) box_y(nm) box_z(nm)` (one row per replica). */
function parseBoxes(raw: string): BoxRow[] {
  const out: BoxRow[] = []
  for (const parts of datRows(raw)) {
    const replica = Number(parts[0])
    const x = Number(parts[2])
    const y = Number(parts[3])
    const z = Number(parts[4])
    if (isNaN(replica) || isNaN(x) || isNaN(y) || isNaN(z)) continue
    out.push({ replica, x, y, z })
  }
  return out
}

export function BoxChart({ data }: { data: StructureData }) {
  const boxes = parseBoxes(data.box ?? "")

  return (
    <div>
      <div className="section-header" style={{ border: "none", paddingBottom: 0 }}>
        <h3 className="section-title">Simulation Box</h3>
        <p className="section-desc" style={{ margin: "4px 0 0", fontSize: 13, color: "var(--body-muted)" }}>
          Box dimensions (nm) of each sample's final structure (relax.gro).
        </p>
      </div>
      {boxes.length === 0 ? (
        <div className="chart-container" style={{ height: 180, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ fontSize: 13, color: "var(--body-muted)" }}>No box data available.</div>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr><th>Replica</th><th>Box X (nm)</th><th>Box Y (nm)</th><th>Box Z (nm)</th><th>Volume (nm³)</th></tr>
          </thead>
          <tbody>
            {boxes.map(b => (
              <tr key={b.replica}>
                <td>{b.replica}</td>
                <td>{b.x.toFixed(3)}</td>
                <td>{b.y.toFixed(3)}</td>
                <td>{b.z.toFixed(3)}</td>
                <td style={{ color: COLOR.accent, fontWeight: 600 }}>{(b.x * b.y * b.z).toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}