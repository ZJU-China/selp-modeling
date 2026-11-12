import { useState } from "react"
import type { ControlDef, FlowTask } from "../types"
import { runControl } from "../api"

// Aggregated control surface for one step. Run controls (start/stop/restart)
// hit the existing task endpoints; view controls switch the results pane below
// rather than navigating away, because the whole point of the flow page is to
// keep every step's controls and results on one screen.
export function TaskControlsCard({
  task,
  activeView,
  onSelectView,
}: {
  task: FlowTask
  activeView: string | null
  onSelectView: (view: string) => void
}) {
  const [pending, setPending] = useState<string | null>(null)
  const [result, setResult] = useState<{ id: string; ok: boolean; message: string } | null>(null)

  const runs = task.controls.filter(c => c.kind === "run")
  const views = task.controls.filter(c => c.kind === "view")

  async function handle(c: ControlDef) {
    if (!c.endpoint) return
    setPending(c.id)
    setResult(null)
    try {
      const r = await runControl(c.endpoint, c.method ?? "POST")
      const message = r.ok
        ? (typeof r.start === "object" ? "Accepted" : "OK")
        : String(r.error ?? "Request failed")
      setResult({ id: c.id, ok: r.ok, message })
    } catch (e) {
      setResult({ id: c.id, ok: false, message: (e as Error).message })
    } finally {
      setPending(null)
    }
  }

  if (runs.length === 0 && views.length === 0) {
    return (
      <div className="flow-panel">
        <div className="flow-panel-head"><h4 className="flow-panel-title">Controls</h4></div>
        <div className="flow-note flow-note-muted">No controls for this step type.</div>
      </div>
    )
  }

  return (
    <div className="flow-panel">
      <div className="flow-panel-head"><h4 className="flow-panel-title">Controls</h4></div>

      <div className="flow-control-rows">
        {runs.length > 0 && (
          <div className="flow-control-row">
            <span className="flow-control-label">Run</span>
            <div className="flow-control-buttons">
              {runs.map(c => (
                <button
                  key={c.id}
                  className={`btn btn-sm${result?.id === c.id && !result.ok ? " btn-danger" : ""}`}
                  disabled={pending !== null}
                  onClick={() => handle(c)}
                >
                  {pending === c.id ? `${c.label}…` : c.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {views.length > 0 && (
          <div className="flow-control-row">
            <span className="flow-control-label">View</span>
            <div className="flow-control-buttons">
              {views.map(c => (
                <button
                  key={c.id}
                  className={`btn btn-sm${activeView === c.view ? " btn-active" : ""}`}
                  onClick={() => c.view && onSelectView(c.view)}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {result && (
        <div className={`flow-note ${result.ok ? "flow-note-ok" : "flow-note-warn"}`}>
          <strong>{result.ok ? "Accepted" : "Failed"}</strong> — {result.message}
        </div>
      )}

      {task.workDir && (
        <div className="flow-note flow-note-muted">
          Working directory: <code>{task.workDir}</code>
          {task.isLocal && <span className="flow-local-tag">runs locally on the backend host</span>}
        </div>
      )}
    </div>
  )
}
