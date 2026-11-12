import type { AnnotationRow, DerivedSequence, FlowListEntry, FlowOverview } from "./types"

// The flow-centric frontend talks to the same backend as the original app; the
// /api proxy is configured in vite.config.ts. Kept in one module so page
// components never hand-roll a fetch.

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`
    try {
      const body = await r.json()
      if (body?.error) detail = body.error
    } catch {}
    throw new Error(detail)
  }
  return r.json() as Promise<T>
}

export function fetchFlowList(): Promise<{ flows: FlowListEntry[]; flowsDir: string }> {
  return getJson("/api/flows/pages")
}

export function fetchFlowOverview(flowId: string): Promise<FlowOverview> {
  return getJson(`/api/flows/${encodeURIComponent(flowId)}/overview`)
}

export async function syncFlowFolders(): Promise<{ flowsDir: string; synced: Array<{ dir: string; tasks: number }> }> {
  const r = await fetch("/api/flows/folders/sync", { method: "POST" })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json()
}

// Run/stop/restart a single step from a flow card. Returns the raw result so
// the card can surface the backend's own error text.
export async function runControl(
  endpoint: string,
  method = "POST",
): Promise<{ ok: boolean; error?: string; [k: string]: unknown }> {
  const r = await fetch(endpoint, { method })
  const text = await r.text()
  let body: Record<string, unknown> = {}
  try { body = JSON.parse(text) } catch { body = { raw: text.slice(0, 300) } }
  return { ok: r.ok, ...body } as { ok: boolean; error?: string; [k: string]: unknown }
}

export function fetchStructure(taskId: string) {
  return getJson<Record<string, never>>(`/api/data/structure?taskId=${encodeURIComponent(taskId)}`)
}

// Reverse a task's structure back to its one-letter input sequence.
//
// 404 means that task simply has no structure, which is a real answer to report
// rather than a failure, so it is returned instead of thrown.
export async function fetchSequenceFromPdb(taskId: string): Promise<DerivedSequence> {
  const r = await fetch(`/api/data/sequence-from-pdb?taskId=${encodeURIComponent(taskId)}`)
  const body = (await r.json().catch(() => ({}))) as DerivedSequence
  if (!r.ok && r.status !== 404) {
    throw new Error(body?.error || `${r.status} ${r.statusText}`)
  }
  return body
}

// Save the editable inputs from the Parameters panel.
//
// The backend validates the sequence and the annotation motifs, then writes
// them to scripts/task_config.json and input/annotations.csv so the task
// re-derives its structure from these values on the next start.
export async function saveTaskParams(
  taskId: string,
  payload: {
    values: Record<string, string>
    annotations: AnnotationRow[]
    /** Task-relative paths of files uploaded alongside the values. */
    files?: Record<string, string | null>
  },
): Promise<{ ok: boolean }> {
  const r = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/params`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  const text = await r.text()
  let body: Record<string, unknown> = {}
  try { body = JSON.parse(text) } catch { body = {} }
  if (!r.ok) {
    throw new Error((body?.error as string) || (body?.raw as string) || `${r.status} ${r.statusText}`)
  }
  return { ok: true }
}

// Upload an input file the task consumes (e.g. a magnetomech field profile).
//
// There is no multipart handling on the server, so the file is read as text and
// posted as a string. The header check that makes an unusable file a visible
// error lives on the save endpoint, so uploading and saving are separate steps.
export async function uploadTaskFile(
  taskId: string,
  path: string,
  content: string,
): Promise<{ ok: boolean; bytes: number }> {
  const r = await fetch("/api/tasks/file-write", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ taskId, path, content }),
  })
  const text = await r.text()
  let body: Record<string, unknown> = {}
  try { body = JSON.parse(text) } catch { body = {} }
  if (!r.ok) {
    throw new Error((body?.error as string) || `${r.status} ${r.statusText}`)
  }
  return { ok: true, bytes: (body?.bytes as number) ?? content.length }
}

// Read a task file back as text, for a Download button on an uploaded file.
export async function readTaskFile(taskId: string, path: string): Promise<string> {
  const body = await getJson<{ content?: string; error?: string }>(
    `/api/tasks/file-read?taskId=${encodeURIComponent(taskId)}&path=${encodeURIComponent(path)}`,
  )
  return body?.content ?? ""
}

// Trigger a browser download of task file content.
export function downloadTextFile(name: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }))
  const a = document.createElement("a")
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export interface ServerSummary {
  id: string
  name?: string
  host: string
  username: string
  connected: boolean
}

export function fetchServers(): Promise<{ servers: ServerSummary[] }> {
  return getJson("/api/servers")
}

export function fetchFlowTemplates(): Promise<{
  templates: Array<{
    id: string
    label: string
    description: string
    steps: Array<{ taskType: string; name: string }>
  }>
}> {
  return getJson("/api/flows/templates")
}

export function createFlowFromTemplate(body: {
  name: string
  template: string
  serverId: string
}): Promise<{ ok: boolean; flow: { id: string; name: string }; error?: string }> {
  return fetch("/api/flows/from-template", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(async r => {
    const d = await r.json()
    if (!r.ok) throw new Error(d.error ?? `${r.status} ${r.statusText}`)
    return d
  })
}
