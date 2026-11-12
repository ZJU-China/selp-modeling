import { useEffect, useState } from "react"
import type { FlowTask } from "../types"

interface FigureRef {
  id: string
  title: string
  kind: string
  path: string
  script?: string
  sources?: string[]
}

type TaskFigures = FigureRef[] | "loading" | "error"

/**
 * Reference tab: lists the metadata source(s) and plotting script behind every
 * figure the Results panel can draw for each step. Figures that only differed
 * by a time segment are merged, so one row may list several source files.
 */
export function FlowReferenceSection({ tasks }: { tasks: FlowTask[] }) {
  const [figures, setFigures] = useState<Record<string, TaskFigures>>({})
  const key = tasks.map(t => t.id).join(",")

  useEffect(() => {
    let alive = true
    tasks.forEach(t => {
      setFigures(prev => ({ ...prev, [t.id]: "loading" }))
      fetch("/api/tasks/" + encodeURIComponent(t.id) + "/figures")
        .then(r => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
        .then(d => {
          if (alive) setFigures(prev => ({ ...prev, [t.id]: d.figures || [] }))
        })
        .catch(() => {
          if (alive) setFigures(prev => ({ ...prev, [t.id]: "error" }))
        })
    })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  const rel = (p: string, workDir: string | null) =>
    workDir && p.startsWith(workDir + "/") ? p.slice(workDir.length + 1) : p

  return (
    <>
      <div className="section-header">
        <h3 className="section-title">Reference</h3>
        <span className="flow-step-count">{tasks.length} step{tasks.length === 1 ? "" : "s"}</span>
      </div>

      <p className="flow-note flow-note-muted">
        Every figure is generated on request by the plotting script from the listed
        metadata (log / xvg / csv / json). Rendered images are never used as sources.
        Figures that differed only by time segment are merged into one chart, so a row
        may list several source files. Each chart carries labelled x and y axes.
      </p>

      {tasks.map(t => {
        const figs = figures[t.id]
        return (
          <section className="flow-ref-card" key={t.id}>
            <div className="flow-ref-head">
              <h4 className="flow-ref-title">
                {t.index + 1}. {t.name}
              </h4>
              <span className="badge">{t.taskType}</span>
            </div>
            <div className="flow-ref-dir">
              Data directory: <code>{t.workDir || "—"}</code>
            </div>

            {figs === "loading" && <div className="flow-ref-empty">Loading sources…</div>}
            {figs === "error" && <div className="flow-ref-empty">Could not load figures for this step.</div>}
            {Array.isArray(figs) && figs.length === 0 && (
              <div className="flow-ref-empty">No figures are generated from this step's data.</div>
            )}
            {Array.isArray(figs) && figs.length > 0 && (
              <table className="flow-ref-table">
                <thead>
                  <tr>
                    <th>Figure</th>
                    <th>Format</th>
                    <th>Source file(s) — metadata</th>
                    <th>Script</th>
                  </tr>
                </thead>
                <tbody>
                  {figs.map(f => {
                    const sources = f.sources && f.sources.length ? f.sources : [f.path]
                    return (
                      <tr key={f.id}>
                        <td>{f.title}</td>
                        <td><code>{f.kind}</code></td>
                        <td className="flow-ref-path" title={sources.join("\n")}>
                          {sources.map(p => (
                            <div key={p}>{rel(p, t.workDir)}</div>
                          ))}
                        </td>
                        <td className="flow-ref-path">{f.script || "figures-service/render_task.py"}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </section>
        )
      })}
    </>
  )
}
