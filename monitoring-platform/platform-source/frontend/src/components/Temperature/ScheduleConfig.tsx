import type { TempConfig } from "./types"

export function ScheduleConfig({ config }: { config: TempConfig }) {
  const rows = [
    { param: "Replicas", value: String(config.num_replicas), desc: "Independent walkers" },
    { param: "Min Temperature", value: `${config.temp_range[0]} K`, desc: "Physiological temperature" },
    { param: "Max Temperature", value: `${config.temp_range[1]} K`, desc: "Enhanced sampling temperature" },
    { param: "Distribution", value: "Exponential", desc: "More walkers at lower temperatures" },
    { param: "Exchange Frequency", value: `Every ${config.steps_per_cycle.toLocaleString()} steps`, desc: "REX attempt interval" },
    { param: "Steps per Cycle", value: config.steps_per_cycle.toLocaleString(), desc: `${(config.steps_per_cycle * 4 / 1000).toFixed(1)} ps (${(config.steps_per_cycle * 0.000004).toFixed(4)} ns) per cycle` },
    { param: "Total Cycles", value: String(config.total_cycles), desc: `${(config.total_cycles * config.steps_per_cycle * 0.000004).toFixed(2)} ns per replica` },
  ]

  return (
    <div className="section">
      <div className="section-header">
        <h3 className="section-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          Temperature Schedule Configuration
        </h3>
      </div>
      <table className="data-table">
        <thead>
          <tr><th>Parameter</th><th>Value</th><th>Description</th></tr>
        </thead>
        <tbody>
          {rows.map(r => <tr key={r.param}><td>{r.param}</td><td>{r.value}</td><td>{r.desc}</td></tr>)}
        </tbody>
      </table>
    </div>
  )
}
