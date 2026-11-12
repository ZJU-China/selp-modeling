import { useState } from "react"
import type { ReactNode } from "react"
import type { FlowTask } from "../types"
import { TASK_STATE_STYLE, TASK_TYPE_LABEL } from "../types"

// One task, rendered inside one of the three aggregate sections (Parameters /
// Results / Control). The section owns the flow-level grouping; this wrapper
// just labels the task and keeps heavy panes (Results) collapsed by default so
// the section stays scannable.
export function FlowTaskPanel({
  task,
  children,
  defaultOpen = false,
  summary,
}: {
  task: FlowTask
  children: ReactNode
  defaultOpen?: boolean
  summary?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  const style = TASK_STATE_STYLE[task.status.state]

  return (
    <div className={`flow-task-panel${open ? " is-open" : ""}`}>
      <div className="flow-task-panel-head" onClick={() => setOpen(o => !o)} role="button" tabIndex={0}
        onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(o => !o) } }}>
        <span className="flow-task-panel-caret" aria-hidden>▸</span>
        <span className="flow-step-badge">{task.index + 1}</span>
        <span className="flow-task-panel-name">{task.name}</span>
        <span className="flow-task-panel-type">{TASK_TYPE_LABEL[task.taskType] ?? task.taskType}</span>
        {summary && !open && <span className="flow-task-panel-summary">{summary}</span>}
        {task.status.progressPct > 0 && task.status.progressPct < 100 && (
          <span className="flow-step-pct">{task.status.progressPct.toFixed(0)}%</span>
        )}
        <span className={`badge ${style.badge}`}>{style.label}</span>
      </div>
      {open && (
        <div className="flow-task-panel-body">
          <div className="flow-status-line">
            <span className={`badge ${style.badge}`}>{style.label}</span>
            <span>{task.status.detail}</span>
            <span className="flow-evidence">source: <code>{task.status.evidence}</code></span>
          </div>
          {children}
        </div>
      )}
    </div>
  )
}

// One-line description of what a step's Results section holds, shown while the
// panel is collapsed so the section reads as an index rather than a wall of
// charts.
export function resultSummary(task: FlowTask): string {
  const a = task.artifacts
  const parts: string[] = []
  if (a.trajectory) parts.push("trajectory")
  if (a.structure.length) parts.push(`structure (${a.structure.length})`)
  if (a.convergence) parts.push("convergence")
  if (a.temperature) parts.push("temperature")
  if (a.magnetomech || a.magnetomechImage) parts.push("field figures")
  return parts.length ? parts.join(" · ") : "no results yet"
}
