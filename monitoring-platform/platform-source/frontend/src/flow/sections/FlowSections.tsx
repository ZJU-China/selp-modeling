import type { FlowTask } from "../types"
import { TaskParamsCard } from "../cards/TaskParamsCard"
import { TaskControlsCard } from "../cards/TaskControlsCard"
import { ComputedFigures } from "../cards/TaskResultsCard"
import { ExecutionCard } from "../cards/ExecutionCard"
import { TaskResultsCard, viewToCategory } from "../cards/TaskResultsCard"
import type { Category } from "../cards/TaskResultsCard"
import { FlowTaskPanel, resultSummary } from "./FlowTaskPanel"

// Top-level section 2 of 4: every step's parameter input in one place. The panel
// body is dispatched by task type (TIGER2 sequence + annotations, GROMACS CG
// crosslink degree, magnetomech applied field), so the section reads as one
// input summary for the whole pipeline rather than per-step columns.
export function FlowParametersSection({ tasks }: { tasks: FlowTask[] }) {
  return (
    <>
      {tasks.map(t => (
        <FlowTaskPanel key={t.id} task={t} defaultOpen>
          <TaskParamsCard params={t.params} taskId={t.id} siblings={tasks} />
        </FlowTaskPanel>
      ))}
    </>
  )
}

// Top-level section 3 of 4: every step's visualisation output, grouped by
// result category (trajectory / structure / convergence / temperature / field).
// Collapsed per step by default with a one-line index, since the expanded panes
// are chart-heavy.
export function FlowResultsSection({
  tasks,
  views,
  onCategoryChange,
}: {
  tasks: FlowTask[]
  views: Record<string, Category>
  onCategoryChange: (taskId: string, c: Category) => void
}) {
  return (
    <>
      {tasks.map(t => (
        <FlowTaskPanel key={t.id} task={t} summary={resultSummary(t)}>
          <TaskResultsCard
            task={t}
            forced={views[t.id] ?? null}
            onCategoryChange={c => onCategoryChange(t.id, c)}
          />
        </FlowTaskPanel>
      ))}
    </>
  )
}

// Top-level section 4 of 4: run + view controls for every step. View buttons
// raise the matching result category so the Results section opens the same tab —
// controls change what you see without navigating away from the flow page.
export function FlowControlsSection({
  tasks,
  views,
  onSelectView,
}: {
  tasks: FlowTask[]
  views: Record<string, string>
  onSelectView: (taskId: string, view: string) => void
}) {
  return (
    <>
      {tasks.map(t => (
        <FlowTaskPanel key={t.id} task={t} defaultOpen>
          <TaskControlsCard
            task={t}
            activeView={views[t.id] ?? null}
            onSelectView={v => onSelectView(t.id, v)}
          />
          <ComputedFigures taskId={t.id} section="control" />
          {/* Where this step runs and how its tools resolve. Kept next to the
              controls because both answer "why did this not run?" -- the
              controls act, this explains. */}
          <ExecutionCard execution={t.execution} />
        </FlowTaskPanel>
      ))}
    </>
  )
}

export { viewToCategory }
