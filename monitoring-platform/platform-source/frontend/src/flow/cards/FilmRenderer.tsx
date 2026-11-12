import { useEffect, useRef } from "react"
import { parseDCD, makeTrajectoryCallback } from "../../components/MolecularViewer"

/** Hidden route used to render the assembly film frame-by-frame from NGL. */
export function FilmRenderer() {
  const hostRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let stage: any = null
    let disposed = false
    Promise.all([
      import("ngl"),
      fetch("/api/data/packing/construction.dcd").then(r => r.arrayBuffer()),
    ]).then(([{ Stage }, buffer]: any[]) => {
      if (disposed || !hostRef.current) return
      stage = new Stage(hostRef.current, { backgroundColor: "white", tooltip: false })
      const parsed = parseDCD(buffer)
      stage.loadFile("/api/data/packing/topo_protein.pdb", { ext: "pdb" }).then((comp: any) => {
        comp.addRepresentation("spacefill", { colorScheme: "chainid", radiusScale: 0.35 })
        const trajElem = comp.addTrajectory(makeTrajectoryCallback(parsed))
        ;(window as any).__film = {
          total: parsed.nframes,
          setFrame: (i: number) => { trajElem.setFrame(i) },
        }
        trajElem.setFrame(0)
        stage.autoView()
        ;(window as any).__filmReady = true
      })
    }).catch((e: any) => {
      ;(window as any).__filmError = String(e?.message || e)
    })
    return () => { disposed = true; if (stage) stage.dispose() }
  }, [])
  return <div ref={hostRef} style={{ position: "fixed", inset: 0, width: "100vw", height: "100vh", background: "#fff", overflow: "hidden" }} />
}
