import { useEffect, useMemo, useState } from "react"
import { PackingTrajectory } from "./PackingTrajectory"
import type { Artifacts, FlowTask } from "../types"
import type { StructureData } from "../../components/Structure/types"
import { stepsPerCycleOf } from "../../components/Structure/types"
import { RgChart } from "../../components/Structure/RgChart"
import { E2eChart } from "../../components/Structure/E2eChart"
import { RmsdChart } from "../../components/Structure/RmsdChart"
import { SsChart } from "../../components/Structure/SsChart"
import { EnergyChart } from "../../components/Structure/EnergyChart"
import { BoxChart } from "../../components/Structure/BoxChart"
import { NetworkChart } from "../../components/Structure/NetworkChart"
import { TrajectoryTab } from "../../components/Structure/TrajectoryTab"
import { TrajectorySection } from "../../components/TrajectorySection"
import { ConvergenceSummary } from "../../components/Convergence/ConvergenceSummary"
import { METRIC_META } from "../../components/Convergence/types"
import type { ConvergenceData, MetricKey } from "../../components/Convergence/types"
import { TemperatureTrace } from "../../components/Temperature/TemperatureTrace"
import { VisitExchange } from "../../components/Temperature/VisitExchange"
import { ReplicaSummary } from "../../components/Temperature/ReplicaSummary"
import { ScheduleConfig } from "../../components/Temperature/ScheduleConfig"
import type { TempData } from "../../components/Temperature/types"

// Result categories, in pipeline order. Each step only renders the categories
// its artefacts actually support, so an unfinished step shows a short honest
// list rather than a grid of "no data" panels.
export type Category = "trajectory" | "structure" | "convergence" | "temperature" | "field"

const CATEGORY_ORDER: Category[] = ["trajectory", "structure", "convergence", "temperature", "field"]

export const CATEGORY_LABEL: Record<Category, string> = {
  trajectory: "Trajectory",
  structure: "Structure",
  convergence: "Convergence",
  temperature: "Temperature",
  field: "Field & deformation",
}

export function availableCategories(task: FlowTask): Category[] {
  const a = task.artifacts
  const out: Category[] = []
  if (a.trajectory) out.push("trajectory")
  if (a.structure.length > 0) out.push("structure")
  if (a.convergence) out.push("convergence")
  if (a.temperature) out.push("temperature")
  if (a.magnetomech || a.magnetomechImage) out.push("field")
  return CATEGORY_ORDER.filter(c => out.includes(c))
}

// The Control section exposes per-step view buttons (backend control id
// "field-deformation" etc.). Map them onto result categories so a button in one
// top-level section selects the matching tab in another.
const VIEW_TO_CATEGORY: Record<string, Category> = {
  trajectory: "trajectory",
  structure: "structure",
  convergence: "convergence",
  temperature: "temperature",
  field: "field",
  "field-deformation": "field",
}

export function viewToCategory(view: string | null | undefined): Category | null {
  if (!view) return null
  return VIEW_TO_CATEGORY[view] ?? null
}

export function TaskResultsCard({
  task,
  forced = null,
  onCategoryChange,
}: {
  task: FlowTask
  forced?: Category | null
  onCategoryChange?: (c: Category) => void
}) {
  const categories = availableCategories(task)
  const [local, setLocal] = useState<Category | null>(null)

  // `forced` (set by the Control section) wins, so a view button there selects
  // the tab here; otherwise fall back to this card's own selection.
  const active: Category = (forced && categories.includes(forced))
    ? forced
    : (local && categories.includes(local) ? local : (categories[0] ?? "structure"))

  const select = (c: Category) => {
    setLocal(c)
    onCategoryChange?.(c)
  }

  if (categories.length === 0) {
    return (
      <div className="flow-panel">
        <div className="flow-panel-head">
          <h4 className="flow-panel-title">Results</h4>
        </div>
        <div className="flow-note flow-note-muted">
          No result artefacts yet for this step. Analysis output appears under
          {" "}<code>tasks/{task.id}/cache/analysis/</code> once the step has run.
        </div>
        <ComputedFigures taskId={task.id} />
      {task.taskType === "gromacs_cg" && task.name.includes("2KY-5") && <PackingTrajectory />}
      </div>
    )
  }

  const current = categories.includes(active) ? active : categories[0]

  return (
    <div className="flow-panel">
      <div className="flow-panel-head">
        <h4 className="flow-panel-title">Results</h4>
        <div className="tabs flow-tabs">
          {categories.map(c => (
            <button
              key={c}
              className={`tab${c === current ? " active" : ""}`}
              onClick={() => select(c)}
            >
              {CATEGORY_LABEL[c]}
            </button>
          ))}
        </div>
      </div>

      {current === "trajectory" && <TrajectoryPane task={task} />}
      {current === "structure" && <StructurePane task={task} />}
      {current === "convergence" && <ConvergencePane task={task} />}
      {current === "temperature" && <TemperaturePane task={task} />}
      {current === "field" && <FieldPane task={task} />}
      <ComputedFigures taskId={task.id} />
      {task.taskType === "gromacs_cg" && task.name.includes("2KY-5") && <PackingTrajectory />}
    </div>
  )
}

function useStructureData(task: FlowTask) {
  const [data, setData] = useState<StructureData | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let alive = true
    setLoading(true)
    fetch(`/api/data/structure?taskId=${encodeURIComponent(task.id)}`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => { if (alive) { setData(d); setLoading(false) } })
      .catch(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [task.id])
  return { data, loading }
}

function StructurePane({ task }: { task: FlowTask }) {
  const { data, loading } = useStructureData(task)
  const available = task.artifacts.structure.map(s => s.key)
  const spc = useMemo(() => stepsPerCycleOf(data), [data])

  if (loading) return <div className="loading">Loading structure analysis…</div>
  if (!data) return <div className="flow-note flow-note-muted">Structure data unavailable.</div>

  return (
    <div className="flow-chart-grid">
      {available.includes("rg") && <RgChart data={data} stepsPerCycle={spc} />}
      {available.includes("e2e") && <E2eChart data={data} stepsPerCycle={spc} />}
      {available.includes("rmsd") && <RmsdChart data={data} stepsPerCycle={spc} />}
      {available.includes("ss") && <SsChart data={data} />}
      {available.includes("chainRg") && <NetworkChart data={data} stepsPerCycle={spc} />}
      {available.includes("energy") && <EnergyChart data={data} stepsPerCycle={spc} />}
      {available.includes("box") && <BoxChart data={data} />}
    </div>
  )
}

function TrajectoryPane({ task }: { task: FlowTask }) {
  const { data } = useStructureData(task)
  const empty = { source: "local", rg: null, e2e: null, rmsd: null, ss: null, energy: null, box: null, crosslink: null, crosslinkTable: null, chainRg: null, meta: null }
  return (
    <TrajectoryTab
      data={data ?? empty}
      taskId={task.id}
      defaultReplicas={task.taskType === "gromacs_cg" ? undefined : [0, 1, 2, 3]}
    />
  )
}

// Convergence is served by its own endpoint and rendered with the existing
// summary/block components rather than re-deriving the verdict here.
// Reuses the original convergence charts (TrajectorySection / ConvergenceSummary)
// rather than re-deriving them, so this pane stays equivalent to the original
// Convergence page. The response shape is ConvergenceData: metrics is keyed by
// MetricKey and the thresholds live under thresholds.metrics.
function ConvergencePane({ task }: { task: FlowTask }) {
  const [data, setData] = useState<ConvergenceData | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true); setFailed(false)
    fetch(`/api/data/convergence?taskId=${encodeURIComponent(task.id)}&detectOnly=1`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(d => { if (alive) { setData(d); setLoading(false) } })
      .catch(() => { if (alive) { setFailed(true); setLoading(false) } })
    return () => { alive = false }
  }, [task.id])

  if (loading) return <div className="loading">Checking convergence…</div>
  if (failed) return <div className="flow-note flow-note-muted">No convergence data for this step. Run trajectory sync first.</div>
  if (!data) return <div className="flow-note flow-note-muted">No convergence data for this step.</div>
  if (data.error) return <div className="flow-note flow-note-warn">{data.error}</div>

  const metricKeys = (Object.keys(METRIC_META) as MetricKey[]).filter(k => data.thresholds?.metrics?.[k] != null)
  const replicaKeys = data.replicas ? Object.keys(data.replicas).map(Number).sort((a, b) => a - b) : []
  const recentWindow = data.cycles?.recent_window ?? 100

  if (metricKeys.length === 0 || replicaKeys.length === 0) {
    return <div className="flow-note flow-note-muted">Convergence analysis is not applicable to this step type.</div>
  }

  return (
    <div className="flow-field-pane">
      {data.converged && (
        <div className="flow-note flow-note-ok">
          ✓ Converged — E2E and Rg stable for {data.stable_checks} consecutive checks.
        </div>
      )}
      {!data.converged && data.stopped && (
        <div className="flow-note flow-note-warn">
          ⏹ Simulation stopped — converged on both E2E and Rg.
        </div>
      )}

      <TrajectorySection
        taskId={task.id}
        recentWindow={recentWindow}
        replicas={replicaKeys}
        singleReplica={task.taskType === "gromacs_cg"}
      />
      <ConvergenceSummary data={data} />

      <div>
        <div className="flow-subpanel-title">Convergence criteria</div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th>Criterion</th>
              <th>Threshold</th>
              {replicaKeys.map(rep => <th key={rep}>Replica {rep}</th>)}
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {metricKeys.map(key => {
              const th = data.thresholds.metrics[key]
              const overall = data.metrics?.[key]
              return (
                <tr key={key}>
                  <td>{METRIC_META[key].label}</td>
                  <td className="flow-suffix">Δmean &amp; σ ratio over {th.block_size} cycles</td>
                  <td>{th.mean_diff} nm · {th.std_ratio}×</td>
                  {replicaKeys.map(rep => {
                    const res = data.replicas[String(rep)]?.metrics?.[key]
                    if (!res) return <td key={rep} className="flow-none">–</td>
                    const ok = res.converged
                    return (
                      <td key={rep} style={{ color: ok ? "var(--success)" : "var(--danger)", fontWeight: ok ? 400 : 600 }}>
                        {res.converged ? "✓" : "✗"}{res.last == null ? " –" : ` ${res.last.toFixed(3)} ${METRIC_META[key].unit}`}
                      </td>
                    )
                  })}
                  <td>
                    <span className={`badge ${overall?.all_converged ? "badge-success" : "badge-warning"}`}>
                      {overall?.all_converged ? "All replicas pass" : `${overall?.converged_replicas ?? 0}/${replicaKeys.length} pass`}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Temperature is read from /api/data/sim-status (the same source the original
// Temperature page uses) and drawn with the original trace / visit-exchange /
// summary / schedule components.
function TemperaturePane({ task }: { task: FlowTask }) {
  const [data, setData] = useState<TempData | null>(null)
  const [loading, setLoading] = useState(true)
  const [animate, setAnimate] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true)
    fetch(`/api/data/sim-status?taskId=${encodeURIComponent(task.id)}`)
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(d => { if (alive) { setData(d); setLoading(false); setAnimate(true) } })
      .catch(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [task.id])

  if (loading) return <div className="loading">Loading temperature data…</div>
  if (!data || !data.config || !data.replicas || Object.keys(data.replicas).length === 0) {
    return <div className="flow-note flow-note-muted">No temperature-exchange data for this step.</div>
  }

  // A single fixed-temperature run has no exchange schedule to plot, so say that
  // rather than drawing a one-line chart.
  if (data.config.method === "GROMACS CG (Martini)") {
    return (
      <div className="flow-note flow-note-muted">
        This step runs at a fixed temperature ({data.config.temp_range?.[0]} K, no replica exchange),
        so temperature-exchange analysis is not applicable.
      </div>
    )
  }

  return (
    <div className="flow-field-pane">
      <TemperatureTrace data={data} animate={animate} />
      <VisitExchange data={data} animate={animate} />
      <ReplicaSummary data={data} />
      <ScheduleConfig config={data.config} />
    </div>
  )
}

// Magnetomech renders the static field figures plus the computed result image.
function FieldPane({ task }: { task: FlowTask }) {
  return (
    <div className="flow-field-pane">
      {task.artifacts.magnetomechImage && (
        <figure className="mm-fig-card">
          <img className="mm-fig-img" src={`/api/data/magnetomech/image?taskId=${encodeURIComponent(task.id)}`} alt="Magnetomech field deformation result" />
          <figcaption className="mm-fig-caption">Computed deformation under the applied field</figcaption>
        </figure>
      )}
      <div className="mm-fig-grid">
        {[
          ["Ez", "Local axial modulus"],
          ["displacement", "Displacement field"],
          ["epsf", "Axial strain"],
          ["porePressure", "Pore pressure"],
          ["stressSzz", "Axial stress"],
          ["magneticField", "Applied field"],
        ].map(([key, label]) => (
          <figure className="mm-fig-card" key={key}>
            <img className="mm-fig-img" src={`/api/data/matlab-figure/${key}`} alt={label} />
            <figcaption className="mm-fig-label">{label}</figcaption>
          </figure>
        ))}
      </div>
    </div>
  )
}

function ComputedFigures({ taskId, section = "results" }: { taskId: string; section?: "results" | "control" }) {
  const [figures, setFigures] = useState<Array<{ id: string; title: string }>>([])
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    let alive = true
    fetch("/api/tasks/" + encodeURIComponent(taskId) + "/figures")
      .then(r => (r.ok ? r.json() : { figures: [] }))
      .then(d => { if (alive) setFigures(d.figures || []) })
      .catch(() => {})
    return () => { alive = false }
  }, [taskId, nonce])
  const shown = figures.filter(f => (f.section || "results") === section)
  if (!shown.length) return null
  return (
    <div className="flow-panel" style={{ marginTop: 12 }}>
      <div className="flow-panel-head">
        <h4 className="flow-panel-title">{section === "control" ? "Control figures" : "Computed figures"}</h4>
        <button className="tab" onClick={() => setNonce(n => n + 1)}>Recompute</button>
      </div>
      <div className="flow-figures">
        {shown.map(f => (
          <figure key={f.id}>
            <img src={"/api/tasks/" + encodeURIComponent(taskId) + "/figures/" + f.id + ".svg?n=" + nonce} alt={f.title} />
            <figcaption>{f.title}</figcaption>
          </figure>
        ))}
      </div>
    </div>
  )
}

export type { Artifacts }
export { ComputedFigures }
