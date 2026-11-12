import { useState } from "react"
import { createFlowFromTemplate, fetchFlowTemplates, fetchServers, type ServerSummary } from "../api"

// Creating a flow from the console.
//
// POST /api/flows/create only makes an empty flow, and building the chain by
// hand means also hand-wiring each step's outputs into the next step's inputs.
// A template encodes that wiring in the same place the steps are created, so the
// two cannot drift apart -- which is why this is a template picker rather than a
// name field plus a separate "add step" button.
export function NewFlowCard({ onCreated }: { onCreated: (flowId: string) => void }) {
  const [servers, setServers] = useState<ServerSummary[]>([])
  const [open, setOpen] = useState(false)
  const [name, setName] = useState("")
  const [template, setTemplate] = useState("full-chain")
  const [serverId, setServerId] = useState("")
  const [templates, setTemplates] = useState<Array<{
    id: string; label: string; description: string
    steps: Array<{ taskType: string; name: string }>
  }>>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function reveal() {
    setOpen(true)
    if (templates.length && servers.length) return
    // Both are needed before the form is usable: the template decides whether a
    // server is required at all, so neither can be skipped.
    const [t, s] = await Promise.allSettled([fetchFlowTemplates(), fetchServers()])
    if (t.status === "fulfilled") setTemplates(t.value.templates)
    else setError((t.reason as Error).message)
    if (s.status === "fulfilled") setServers(s.value.servers)
    else setError((s.reason as Error).message)
  }

  const selected = templates.find(t => t.id === template)
  const needsServer = !!selected && selected.steps.some(s =>
    s.taskType !== "magnetomech")

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const d = await createFlowFromTemplate({ name, template, serverId })
      onCreated(d.flow.id)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button className="btn btn-primary btn-sm" onClick={reveal}>
        + New flow
      </button>
    )
  }

  return (
    <div className="flow-panel">
      <div className="flow-panel-head">
        <h4 className="flow-panel-title">New flow</h4>
        <button className="btn btn-sm" onClick={() => setOpen(false)}>Cancel</button>
      </div>

      <div className="flow-new-rows">
        <label className="flow-new-field">
          <span>Name</span>
          <input
            className="input"
            value={name}
            autoFocus
            placeholder="e.g. TF E2E validation"
            onChange={e => setName(e.target.value)}
          />
        </label>

        <label className="flow-new-field">
          <span>Template</span>
          <select className="input" value={template} onChange={e => setTemplate(e.target.value)}>
            {templates.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </label>

        {selected && <div className="flow-note flow-note-muted">{selected.description}</div>}

        {selected && selected.steps.length > 0 && (
          <div className="flow-note flow-note-muted">
            Steps, in order:{" "}
            {selected.steps.map((s, i) => (
              <span key={i}>
                {i > 0 && " → "}
                <code>{s.name}</code>
              </span>
            ))}
          </div>
        )}

        {needsServer && (
          <label className="flow-new-field">
            <span>Server for the compute steps</span>
            <select className="input" value={serverId} onChange={e => setServerId(e.target.value)}>
              <option value="">Choose a server…</option>
              {servers.map(s => (
                <option key={s.id} value={s.id}>{s.name ?? `${s.username}@${s.host}`}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      {error && <div className="flow-note flow-note-warn">{error}</div>}

      <div className="flow-control-buttons">
        <button
          className="btn btn-primary btn-sm"
          disabled={busy || !name.trim() || (needsServer && !serverId)}
          onClick={submit}
        >
          {busy ? "Creating…" : "Create flow"}
        </button>
      </div>
    </div>
  )
}
