import { useEffect, useRef, useState } from "react"
import { parseDCD, makeTrajectoryCallback } from "../../components/MolecularViewer"

/**
 * Flow-only 3D viewer for the packed 32-chain precursor system.
 * Uses the platform's DCD parser (same code path as MolecularViewer):
 * the protein-only trajectory is fetched, parsed, and injected as a
 * trajectory callback so NGL can play it.
 */
export function PackingTrajectory({ height = 440 }: { height?: number }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const playerRef = useRef<any>(null)
  const [playing, setPlaying] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let disposed = false
    let stage: any = null
    Promise.all([
      import("ngl"),
      fetch("/api/data/packing/traj_protein.dcd").then(r => r.arrayBuffer()),
    ])
      .then(([{ Stage, TrajectoryPlayer }, buffer]: any[]) => {
        if (disposed || !hostRef.current) return
        stage = new Stage(hostRef.current, { backgroundColor: "white", tooltip: false })
        const parsed = parseDCD(buffer)
        return stage
          .loadFile("/api/data/packing/topo_protein.pdb", { ext: "pdb" })
          .then((comp: any) => {
            comp.addRepresentation("spacefill", { colorScheme: "chainid", radiusScale: 0.22 })
            const trajElem = comp.addTrajectory(makeTrajectoryCallback(parsed) as any)
            const traj = trajElem.trajectory
            const player = new TrajectoryPlayer(traj, {
              step: 1, timeout: 1000 / 10, mode: "loop", direction: "forward",
            })
            playerRef.current = player
            try { trajElem.setFrame(0) } catch (_) {}
            setTimeout(() => {
              try { player.play() } catch (_) {}
              try { stage.autoView() } catch (_) {}
            }, 400)
          })
      })
      .catch((e: any) => setError(String(e?.message || e)))
    return () => {
      disposed = true
      if (stage) stage.dispose()
    }
  }, [])

  const toggle = () => {
    const p = playerRef.current
    if (!p) return
    p.toggle()
    setPlaying(p.isPlaying !== false)
  }

  return (
    <figure className="mm-fig-card flow-packing">
      <div className="flow-packing-head">
        <h4 className="flow-panel-title">Packed 32-chain system · dynamic trajectory</h4>
        <button className="tab" onClick={toggle}>{playing ? "Pause" : "Play"}</button>
      </div>
      <div ref={hostRef} className="flow-packing-stage" style={{ height }} />
      {error && <div className="flow-ref-empty">Could not load trajectory: {error}</div>}
      <figcaption className="mm-fig-caption">
        Chains coloured by chain ID; solvent hidden. 51 frames from the 5 ns precursor run.
      </figcaption>
    </figure>
  )
}
