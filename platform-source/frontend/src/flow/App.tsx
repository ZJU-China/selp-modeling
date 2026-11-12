import { useEffect, useState } from "react"
import { NewFlowCard } from "./cards/NewFlowCard"
import { FilmRenderer } from "./cards/FilmRenderer"
import { FilmInteractive } from "./cards/FilmInteractive"
import { fetchFlowList, fetchFlowOverview, syncFlowFolders } from "./api"
import type { FlowListEntry, FlowOverview } from "./types"
import { TASK_STATE_STYLE } from "./types"
import { FlowProgressCard } from "./cards/FlowProgressCard"
import { FlowParametersSection, FlowResultsSection, FlowControlsSection, viewToCategory } from "./sections/FlowSections"
import { FlowReferenceSection } from "./sections/FlowReferenceSection"
import type { Category } from "./cards/TaskResultsCard"

// URL routing: /            -> flow list
//             /flow/:id    -> one flow
// The original app routes via a localStorage "page" string, which makes a flow
// page unlinkable and breaks back/forward. Flow pages are meant to be shared,
// so this app uses real paths.
function useHashRoute(): [string, (to: string) => void] {
  const [hash, setHash] = useState(() => window.location.hash)
  useEffect(() => {
    const on = () => setHash(window.location.hash)
    window.addEventListener("hashchange", on)
    return () => window.removeEventListener("hashchange", on)
  }, [])
  const navigate = (to: string) => { window.location.hash = to }
  return [hash, navigate]
}

// The four top-level blocks of a flow page, in reading order.
const FLOW_BLOCKS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "parameters", label: "Parameters" },
  { id: "results", label: "Results" },
  { id: "control", label: "Control" },
  { id: "reference", label: "Reference" },
] as const

export function App() {
  const [hash, navigate] = useHashRoute()
  // #/flow/<id>            -> Dashboard (default)
  // #/flow/<id>/<block>    -> that block, deep-linkable
  const m = /^#\/flow\/([^/]+)(?:\/([a-z]+))?$/i.exec(hash)
  const flowId = m?.[1] ? decodeURIComponent(m[1]) : undefined
  const blockParam = m?.[2]?.toLowerCase()
  const activeBlock = FLOW_BLOCKS.some(b => b.id === blockParam) ? blockParam! : "dashboard"

  if (hash === "#/film-render") return <FilmRenderer />
  if (hash === "#/film-interactive") return <FilmInteractive />
  if (flowId) return <FlowPage flowId={flowId} activeBlock={activeBlock} navigate={navigate} />
  return <FlowListPage navigate={navigate} />
}

function FlowListPage({ navigate }: { navigate: (to: string) => void }) {
  const [flows, setFlows] = useState<FlowListEntry[] | null>(null)
  const [flowsDir, setFlowsDir] = useState<string>("")
  const [error, setError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)

  const load = () => {
    setError(null)
    fetchFlowList()
      .then(d => { setFlows(d.flows); setFlowsDir(d.flowsDir) })
      .catch(e => setError(e.message))
  }
  useEffect(load, [])

  return (
    <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>
      <div className="hero" style={{ textAlign: "center" }}>
        <h1>Flow Console</h1>
        <p className="hero-subtitle" style={{ margin: "0 auto" }}>
          Pipeline-centric view — one page per flow
        </p>
      </div>

      <div className="section">
        <div className="section-header">
          <h3 className="section-title">Flows</h3>
          <div className="flow-header-actions">
            <button className="btn btn-sm" onClick={load}>Refresh</button>
            <NewFlowCard onCreated={id => navigate(`#/flow/${encodeURIComponent(id)}`)} />
            <button
              className="btn btn-sm"
              disabled={syncing}
              onClick={async () => {
                setSyncing(true)
                try { await syncFlowFolders(); load() } catch (e) { setError((e as Error).message) }
                finally { setSyncing(false) }
              }}
            >
              {syncing ? "Syncing…" : "Sync flow folders"}
            </button>
          </div>
        </div>

        {error && <div className="empty-state">Error: {error}</div>}
        {!flows && !error && <div className="loading">Loading flows…</div>}
        {flows && flows.length === 0 && <div className="empty-state">No flows defined.</div>}

        {flows && flows.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Flow</th>
                <th>Steps</th>
                <th>Progress</th>
                <th>Reached</th>
                <th>Folder</th>
              </tr>
            </thead>
            <tbody>
              {flows.map(f => (
                <tr key={f.id} onClick={() => navigate(`#/flow/${encodeURIComponent(f.id)}`)} style={{ cursor: "pointer" }}>
                  <td><strong>{f.name}</strong></td>
                  <td>{f.taskCount}</td>
                  <td>
                    <div className="flow-mini-bar">
                      <div className="flow-mini-fill" style={{ width: `${Math.max(f.progress.clearedPct, 1)}%` }} />
                    </div>
                    <span className="flow-mini-label">{f.progress.doneCount}/{f.progress.total} · {f.progress.clearedPct}%</span>
                  </td>
                  <td>
                    {f.progress.complete
                      ? <span className="badge badge-success">Complete</span>
                      : <span>Step {f.progress.reachedIndex + 1} — {f.progress.reachedTaskName}</span>}
                  </td>
                  <td><code>flows/{f.folder}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {flowsDir && (
          <div className="flow-note flow-note-muted">
            Per-flow task copies are written under <code>{flowsDir}</code>. The store at
            {" "}<code>backend/tasks.json</code> remains the single source of truth.
          </div>
        )}
      </div>
    </div>
  )
}

function FlowPage({
  flowId,
  activeBlock,
  navigate,
}: {
  flowId: string
  activeBlock: string
  navigate: (to: string) => void
}) {
  const [overview, setOverview] = useState<FlowOverview | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Result category selected per task. Shared by the Control section's view
  // buttons and the Results section's tab bar so the two stay in sync.
  const [views, setViews] = useState<Record<string, Category>>({})

  const load = () => {
    setError(null)
    fetchFlowOverview(flowId)
      .then(setOverview)
      .catch(e => setError(e.message))
  }
  useEffect(() => {
    load()
    const t = setInterval(load, 30_000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flowId])

  if (error) {
    return (
      <div className="container" style={{ padding: 48 }}>
        <button className="btn btn-sm" onClick={() => navigate("#/")}>← All flows</button>
        <div className="empty-state">Error: {error}</div>
      </div>
    )
  }
  if (!overview) {
    return <div className="container loading" style={{ padding: 48 }}>Loading flow…</div>
  }

  const { flow, progress, tasks } = overview

  return (
    <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>
      <div className="flow-back-row">
        <button className="btn btn-sm" onClick={() => navigate("#/")}>← All flows</button>
        <code className="flow-id">{flow.id}</code>
      </div>

      <div className="hero" style={{ textAlign: "center" }}>
        <h1>{flow.name}</h1>
        <p className="hero-subtitle" style={{ margin: "0 auto" }}>
          {progress.total} step{progress.total === 1 ? "" : "s"} · {progress.doneCount} complete
          {progress.complete
            ? " · pipeline finished"
            : progress.outOfOrder
              ? ` · reached step ${progress.reachedIndex + 1}, step ${progress.currentIndex + 1} still running`
              : ` · currently at step ${progress.currentIndex + 1}`}
        </p>
        <div className="flow-hero-badges">
          <span className={`badge ${progress.complete ? "badge-success" : progress.outOfOrder ? "badge-warning" : "badge-info"}`}>
            {progress.complete ? "Complete" : progress.outOfOrder ? "Step re-running" : "In progress"}
          </span>
          {tasks.map(t => (
            <span key={t.id} className={`badge ${TASK_STATE_STYLE[t.status.state].badge}`}>
              {t.index + 1}. {t.taskType}
            </span>
          ))}
        </div>
      </div>

      {/* The four blocks are tabs, not stacked sections: only the selected one
          is mounted, so switching does not run three sets of chart queries at
          once. The active block lives in the URL, so a specific view of a flow
          is still linkable. */}
      <nav className="flow-block-tabs" role="tablist">
        {FLOW_BLOCKS.map(b => {
          const on = b.id === activeBlock
          return (
            <button
              key={b.id}
              role="tab"
              aria-selected={on}
              className={`flow-block-tab${on ? " is-active" : ""}`}
              onClick={() => navigate(`#/flow/${encodeURIComponent(flowId)}/${b.id}`)}
            >
              {b.label}
            </button>
          )
        })}
      </nav>

      <div className="flow-block" role="tabpanel">
        {activeBlock === "dashboard" && (
          <>
            <div className="section-header">
              <h3 className="section-title">Dashboard</h3>
              <span className={`badge ${progress.complete ? "badge-success" : "badge-info"}`}>
                {progress.doneCount} / {progress.total} steps complete
              </span>
            </div>
            <FlowProgressCard progress={progress} />
          </>
        )}

        {activeBlock === "parameters" && (
          <>
            <div className="section-header">
              <h3 className="section-title">Parameters</h3>
              <span className="flow-step-count">{tasks.length} step{tasks.length === 1 ? "" : "s"}</span>
            </div>
            <FlowParametersSection tasks={tasks} />
          </>
        )}

        {activeBlock === "results" && (
          <>
            <div className="section-header">
              <h3 className="section-title">Results</h3>
              <span className="flow-step-count">{tasks.length} step{tasks.length === 1 ? "" : "s"}</span>
            </div>
            <FlowResultsSection
              tasks={tasks}
              views={views}
              onCategoryChange={(taskId, c) => setViews(v => ({ ...v, [taskId]: c }))}
            />
          </>
        )}

        {activeBlock === "reference" && (
          <FlowReferenceSection tasks={tasks} />
        )}

        {activeBlock === "control" && (
          <>
            <div className="section-header">
              <h3 className="section-title">Control</h3>
              <span className="flow-step-count">{tasks.length} step{tasks.length === 1 ? "" : "s"}</span>
            </div>
            <FlowControlsSection
              tasks={tasks}
              views={views}
              onSelectView={(taskId, view) => {
                const cat = viewToCategory(view)
                if (cat) setViews(v => ({ ...v, [taskId]: cat }))
              }}
            />
          </>
        )}
      </div>

      <div className="flow-note flow-note-muted">
        Flow folder: <code>{overview.folderPath}</code> — {overview.sourceOfTruth}
      </div>
    </div>
  )
}
