import type { FlowProgress } from "../types"
import { TASK_STATE_STYLE, TASK_TYPE_LABEL } from "../types"

// Overall flow progress. Two distinct measures, deliberately not conflated:
//
//   clearedPct  fraction of steps finished          (0% cleared while stuck)
//   stepPct     how far along the bar the current step sits
//
// A pipeline stalled on step 2 of 5 is 0% cleared but 25% along the bar, and
// showing "0%" for that would read as "nothing has happened".
export function FlowProgressCard({ progress }: { progress: FlowProgress }) {
  const { total, steps, currentIndex } = progress
  if (total === 0) {
    return <div className="empty-state">This flow has no steps yet.</div>
  }

  return (
    <div>
      <div className="flow-progress-summary">
        <div className="flow-progress-metric">
          <span className="stat-value">{progress.clearedPct}%</span>
          <span className="stat-label">Steps cleared</span>
        </div>
        <div className="flow-progress-metric">
          <span className="stat-value">
            {progress.currentTaskName ? `Step ${progress.reachedIndex + 1}` : "—"}
          </span>
          <span className="stat-label">Reached</span>
        </div>
        <div className="flow-progress-metric flow-progress-current">
          <span className="stat-value stat-value-sm">
            {progress.complete
              ? "All steps complete"
              : progress.outOfOrder
                ? `${progress.currentTaskName} (still running behind step ${progress.reachedIndex + 1})`
                : progress.currentTaskName}
          </span>
          <span className="stat-label">
            {progress.complete ? "Pipeline finished" : "Active step"}
          </span>
        </div>
      </div>

      <div className="flow-progress-track" role="progressbar" aria-valuenow={Math.round(progress.stepPct)} aria-valuemin={0} aria-valuemax={100}>
        <div className="flow-progress-fill" style={{ width: `${Math.max(progress.stepPct, 2)}%` }} />
        {steps.map((s, i) => (
          <div
            key={s.id}
            className={`flow-progress-node flow-node-${s.state.toLowerCase()}${i === currentIndex && !progress.complete ? " is-current" : ""}`}
            style={{ left: `${total > 1 ? (i / (total - 1)) * 100 : 50}%` }}
            title={`${i + 1}. ${s.name} — ${TASK_STATE_STYLE[s.state].label}`}
          />
        ))}
      </div>

      <ol className="flow-step-list">
        {steps.map((s, i) => {
          const style = TASK_STATE_STYLE[s.state]
          // Highlight the step work is happening on, not the furthest reached:
          // when they differ the list should point at the live step.
          const isCurrent = i === currentIndex && !progress.complete
          return (
            <li key={s.id} className={`flow-step${isCurrent ? " is-current" : ""}${s.state === "DONE" ? " is-done" : ""}`}>
              <span className={`flow-step-index ${isCurrent ? "is-current" : ""}`}>{i + 1}</span>
              <div className="flow-step-body">
                <div className="flow-step-name">{s.name}</div>
                <div className="flow-step-type">{TASK_TYPE_LABEL[s.taskType] ?? s.taskType}</div>
                {!isCurrent && s.progressPct > 0 && s.progressPct < 100 && (
                  <div className="flow-step-bar">
                    <div className="flow-step-bar-fill" style={{ width: `${s.progressPct}%` }} />
                  </div>
                )}
              </div>
              <span className={`badge ${style.badge}`}>{style.label}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
