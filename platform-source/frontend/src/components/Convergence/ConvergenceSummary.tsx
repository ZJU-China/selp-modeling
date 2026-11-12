import type { ConvergenceData } from "./types"

interface Props {
  data: ConvergenceData
}

export function ConvergenceSummary({ data }: Props) {
  const cycles = data.cycles || { block_size: 25, total: 0, in_block: 0 }
  const hasData = cycles.total > 0

  return (
    <div className="stats-panel">
      <div className="stat-card">
        <div className="stat-value">
          {hasData ? `${cycles.in_block} / ${cycles.block_size}` : "—"}
        </div>
        <div className="stat-label">Current cycle within {cycles.block_size}-cycle window</div>
      </div>
      <div className="stat-card">
        <div className="stat-value">
          {hasData ? `${cycles.total}` : "—"}
          <span style={{ fontSize: 16, color: "var(--body-muted)" }}> cycles</span>
        </div>
        <div className="stat-label">Total cycles elapsed</div>
      </div>
    </div>
  )
}
