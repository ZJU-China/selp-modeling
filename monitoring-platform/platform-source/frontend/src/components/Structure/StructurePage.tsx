import { useState, useEffect } from "react"
import { TrajectoryTab } from "./TrajectoryTab"
import { RgChart } from "./RgChart"
import { E2eChart } from "./E2eChart"
import { RmsdChart } from "./RmsdChart"
import { SsChart } from "./SsChart"
import { EnergyChart } from "./EnergyChart"
import { BoxChart } from "./BoxChart"
import { NetworkChart } from "./NetworkChart"
import { CrosslinkChart } from "./CrosslinkChart"
import { stepsPerCycleOf, type StructureData } from "./types"

export type { StructureData }

interface TabDef {
  id: string
  label: string
  component: React.ComponentType<any>
  extraProps?: (data: StructureData, taskId: string, taskType?: string) => Record<string, unknown>
}

const TABS: TabDef[] = [
  {
    id: "trajectory", label: "MD Trajectory", component: TrajectoryTab,
    // GROMACS CG converts one DCD per sample, so the viewer's replica buttons
    // are driven by the trajectory status (how many samples were converted);
    // TIGER2 defaults to its 4-replica ladder. Both are overridden by the
    // status when it reports per-replica DCDs.
    extraProps: (_data, taskId, taskType) => ({
      taskId,
      defaultReplicas: taskType === "gromacs_cg" ? undefined : [0, 1, 2, 3],
    }),
  },
  { id: "rg", label: "Radius of Gyration", component: RgChart },
  { id: "e2e", label: "End-to-End Distance", component: E2eChart },
  { id: "rmsd", label: "RMSD", component: RmsdChart },
  { id: "ss", label: "Secondary Structure", component: SsChart },
]

// GROMACS CG analysis tabs — one per output produced by analyze.py. Steps per
// cycle comes from meta.json (falls back to the TIGER2 15000 default).
const CG_TABS: TabDef[] = [
  {
    id: "trajectory", label: "MD Trajectory", component: TrajectoryTab,
    extraProps: (_data, taskId, taskType) => ({
      taskId,
      defaultReplicas: taskType === "gromacs_cg" ? undefined : [0, 1, 2, 3],
    }),
  },
  { id: "rg", label: "Radius of Gyration", component: RgChart, extraProps: d => ({ stepsPerCycle: stepsPerCycleOf(d) }) },
  { id: "e2e", label: "End-to-End Distance", component: E2eChart, extraProps: d => ({ stepsPerCycle: stepsPerCycleOf(d) }) },
  { id: "rmsd", label: "RMSD", component: RmsdChart, extraProps: d => ({ stepsPerCycle: stepsPerCycleOf(d) }) },
  { id: "chainRg", label: "Per-chain Rg", component: NetworkChart, extraProps: d => ({ stepsPerCycle: stepsPerCycleOf(d) }) },
  { id: "crosslink", label: "Crosslinks", component: CrosslinkChart, extraProps: d => ({ stepsPerCycle: stepsPerCycleOf(d) }) },
  { id: "energy", label: "Energy & Temperature", component: EnergyChart, extraProps: d => ({ stepsPerCycle: stepsPerCycleOf(d) }) },
  { id: "box", label: "Box Size", component: BoxChart },
]

const ANALYSIS_TOOLS = [
  { property: "Radius of Gyration", tool: "MDAnalysis", description: "Compactness measure of the polymer chain" },
  { property: "End-to-End Distance", tool: "MDAnalysis", description: "Distance between N-terminus and C-terminus" },
  { property: "RMSD", tool: "MDAnalysis", description: "Structural deviation from reference frame" },
  { property: "Secondary Structure", tool: "MDAnalysis (DSSP)", description: "α-helix, β-sheet, coil content over time" },
]

export function StructurePage({ selectedTask }: { selectedTask: { id: string; name: string; taskType?: string } | null }) {
  const [data, setData] = useState<StructureData | null>(null)
  const [activeTab, setActiveTab] = useState(TABS[0].id)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!selectedTask) return
    setLoading(true)
    setError(null)

    fetch(`/api/data/structure?taskId=${selectedTask.id}`)
      .then(r => r.json())
      .then(structData => {
        setData(structData)
        setLoading(false)
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [selectedTask?.id])

  if (!selectedTask) return <div className="container" style={{ padding: 48 }}><div className="empty-state">Select a task in the header to view structural analysis.</div></div>
  if (loading) return <div className="container loading" style={{ padding: 48 }}>Loading structure data via SSH...</div>
  if (error) return <div className="container" style={{ padding: 48 }}><div className="empty-state">Error: {error}</div></div>
  if (!data) return <div className="container" style={{ padding: 48 }}><div className="empty-state">No data available.</div></div>

  const isGcTask = selectedTask.taskType === "gromacs_cg"
  const hasRealData = isGcTask
    ? data.rg || data.e2e || data.rmsd || data.energy || data.box || data.crosslink || data.chainRg
    : data.rg || data.e2e || data.rmsd || data.ss

  const tabs = isGcTask ? CG_TABS : TABS
  if (!tabs.some(t => t.id === activeTab)) {
    setActiveTab(tabs[0].id)
  }

  return (
    <div className="container" style={{ paddingTop: 24, paddingBottom: 48 }}>
      <div className="hero" style={{ textAlign: "center" }}>
        <h1>Structural Analysis</h1>
        <p className="hero-subtitle" style={{ margin: "0 auto" }}>
          2KY10 SELP · {hasRealData ? "Data fetched via SSH from " + selectedTask.name : "Analysis data pending — showing preview"}
        </p>
      </div>

      <div className="section">
        <div className="tabs">
          {tabs.map(t => (
            <button key={t.id} className={`tab ${activeTab === t.id ? "active" : ""}`} onClick={() => setActiveTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>

        {tabs.filter(t => t.id === activeTab).map(t => {
          const Component = t.component
          const extra = t.extraProps ? t.extraProps(data, selectedTask.id, selectedTask.taskType) : {}
          return <Component key={t.id} data={data} {...extra} />
        })}
      </div>

      {!isGcTask && (
        <div className="section">
          <div className="section-header">
            <h3 className="section-title">Analysis Configuration</h3>
          </div>
          <table className="data-table">
            <thead>
              <tr><th>Property</th><th>Tool</th><th>Description</th></tr>
            </thead>
            <tbody>
              {ANALYSIS_TOOLS.map(tool => (
                <tr key={tool.property}><td>{tool.property}</td><td>{tool.tool}</td><td>{tool.description}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}