import type { Execution } from "../types"

// Where a step runs and how its external tools are invoked.
//
// This exists because that information was otherwise only in
// backend/tasks.json. Two specific things it makes visible:
//
//   * the real target -- a flow page previously did not say whether a step ran
//     on this machine or over SSH, and to which host
//   * whether the tools resolve -- gmx and MATLAB are both frequently absent or
//     at a nonstandard path, and a bad value previously surfaced only as a
//     failed run, after the user had waited for it
export function ExecutionCard({ execution }: { execution?: Execution }) {
  if (!execution) return null
  const { connection, paths, tools } = execution
  const toolEntries = tools
    ? Object.entries(tools).filter(([key]) => !key.startsWith("_"))
    : []

  return (
    <div className="flow-panel">
      <div className="flow-panel-head">
        <h4 className="flow-panel-title">Execution</h4>
        <span className={`flow-exec-mode flow-exec-mode-${connection.mode}`}>
          {connection.mode === "local" ? "local" : connection.mode}
        </span>
      </div>

      <div className="flow-exec-rows">
        <div className="flow-exec-row">
          <span className="flow-exec-label">Runs on</span>
          <span className="flow-exec-value">{connection.label}</span>
        </div>

        {connection.namdBin && (
          <div className="flow-exec-row">
            <span className="flow-exec-label">NAMD</span>
            <code className="flow-exec-value">{connection.namdBin}</code>
          </div>
        )}

        <div className="flow-exec-row">
          <span className="flow-exec-label">Input</span>
          <code className="flow-exec-value">{paths.input}</code>
        </div>
        <div className="flow-exec-row">
          <span className="flow-exec-label">Output</span>
          <code className="flow-exec-value">{paths.output}</code>
        </div>
        {paths.remoteWorkDir && (
          <div className="flow-exec-row">
            <span className="flow-exec-label">Remote dir</span>
            <code className="flow-exec-value">{paths.remoteWorkDir}</code>
          </div>
        )}

{toolEntries.map(([key, toolRaw]) => {
          const tool = toolRaw as any;
          return (
          <div className="flow-exec-row" key={key}>
            <span className="flow-exec-label">{(tool as any).name}</span>
            <span className="flow-exec-value">
              <code className={(tool as any).ok ? "" : "flow-exec-bad"}>
                {(tool as any).command}
              </code>
{((tool as any).ok && (tool as any).resolvedTo) && (
                <span className="flow-exec-resolved"> → {(tool as any).resolvedTo}</span>
              )}
              {(tool as any).viaContainer && <span className="flow-local-tag">in container</span>}
              {(!(tool as any).ok && (tool as any).error) && (
                <span className="flow-exec-error"> — {String((tool as any).error)}</span>
              )}
            </span>
          </div>
          );
        })}
      </div>

      {(tools && (tools as any)._host) && (
        <div className="flow-note flow-note-muted">
        </div>
      )}
    </div>
  )
}