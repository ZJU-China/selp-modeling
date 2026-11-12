import { useEffect, useRef, useState } from "react"
import { parseDCD, makeTrajectoryCallback } from "../../components/MolecularViewer"

const REPS: Record<string, any> = {
  sphere: { name: "spacefill", params: { colorScheme: "chainid", radiusScale: 0.3 } },
  stick: { name: "licorice", params: { colorScheme: "chainid" } },
  line: { name: "line", params: { colorScheme: "chainid" } },
}

export function FilmInteractive() {
  const hostRef = useRef<HTMLDivElement>(null)
  const trajAA = useRef<any>(null)
  const trajCG = useRef<any>(null)
  const compAA = useRef<any>(null)
  const compCG = useRef<any>(null)
  const repAA = useRef<any>(null)
  const repCG = useRef<any>(null)
  const stageRef = useRef<any>(null)
  const aaMode = useRef<"cartoon" | "beads">("cartoon")
  const foldN = useRef(0)
  const aaN = useRef(0)
  const cgN = useRef(0)
  const playingRef = useRef(true)
  const frameRef = useRef(0)
  const totalRef = useRef(0)
  const [playing, setPlaying] = useState(true)
  const [frame, setFrame] = useState(0)
  const [total, setTotal] = useState(0)
  const [foldFrames, setFoldFrames] = useState(0)
  const [aaFrames, setAaFrames] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [representation, setRepresentation] = useState("sphere")
  const lastFit = useRef(0)

  const setAaRep = (mode: "cartoon" | "beads") => {
    if (aaMode.current === mode || !compAA.current) return
    if (repAA.current) compAA.current.removeRepresentation(repAA.current)
    repAA.current = mode === "cartoon"
      ? compAA.current.addRepresentation("spacefill", { color: 0xffffff, radiusScale: 0.3 })
      : compAA.current.addRepresentation("spacefill", { colorScheme: "chainid", radiusScale: 0.3 })
    aaMode.current = mode
  }

const COLLAPSE_SPEED = 4
  const displayCount = () => {
    const fold = foldN.current
    const collapse = Math.ceil(Math.max(0, aaN.current - fold) / COLLAPSE_SPEED)
    return fold + collapse + cgN.current
  }
  const mapDisplay = (idx: number) => {
    const fold = foldN.current
    if (idx < fold) return { aa: idx, phase: "fold" as const }
    const collapseFrames = Math.ceil(Math.max(0, aaN.current - fold) / COLLAPSE_SPEED)
    const rest = idx - fold
    if (rest < collapseFrames) {
      const span = Math.max(1, aaN.current - 1 - fold)
      const denom = Math.max(1, collapseFrames - 1)
      return { aa: Math.min(aaN.current - 1, fold + Math.round(rest * span / denom)), phase: "collapse" as const }
    }
    return { cg: idx - fold - collapseFrames, phase: "cg" as const }
  }
  const frameOblique = (comp: any) => {
    if (!comp) return
    try { comp.autoView() } catch (_) {}
  }

  const frameObliqueSmooth = (comp: any, alpha = 0.12) => {
    const stage = stageRef.current
    if (!stage || !comp) return
    try {
      const st = comp.structure.atomStore
      let minx = 1e9, miny = 1e9, minz = 1e9, maxx = -1e9, maxy = -1e9, maxz = -1e9
      for (let i = 0; i < st.count; i++) {
        const x = st.x[i], y = st.y[i], z = st.z[i]
        if (x < minx) minx = x; if (x > maxx) maxx = x
        if (y < miny) miny = y; if (y > maxy) maxy = y
        if (z < minz) minz = z; if (z > maxz) maxz = z
      }
      const cx = (minx + maxx) / 2, cy = (miny + maxy) / 2, cz = (minz + maxz) / 2
      const sx = maxx - minx, sy = maxy - miny, sz = maxz - minz
      const r = 0.5 * Math.sqrt(sx * sx + sy * sy + sz * sz)
      const d = Math.max(30, r * 2.6)
      const cam = stage.viewer.camera
      const tx = cx + d * 0.8, ty = cy - d * 0.8, tz = cz + d * 0.6
      const target = cam.position.clone().set(tx, ty, tz)
      cam.position.lerp(target, alpha)
      const upTarget = cam.up.clone().set(0, 0, 1)
      cam.up.lerp(upTarget, alpha).normalize()
      const look = cam.position.clone().set(cx, cy, cz)
      cam.lookAt(look)
      stage.viewer.requestRender()
    } catch (_) {
      try { comp.autoView() } catch (_) {}
    }
  }

  const orbitAngle = useRef(0)
  const orbitDist = useRef(0)
  const orbitAA = (comp: any) => {
    const stage = stageRef.current
    if (!stage || !comp) return
    try {
      const st = comp.structure.atomStore
      let minx = 1e9, miny = 1e9, minz = 1e9, maxx = -1e9, maxy = -1e9, maxz = -1e9
      for (let i = 0; i < st.count; i++) {
        const x = st.x[i], y = st.y[i], z = st.z[i]
        if (x < minx) minx = x; if (x > maxx) maxx = x
        if (y < miny) miny = y; if (y > maxy) maxy = y
        if (z < minz) minz = z; if (z > maxz) maxz = z
      }
      const cx = (minx + maxx) / 2, cy = (miny + maxy) / 2, cz = (minz + maxz) / 2
      const sx = maxx - minx, sy = maxy - miny, sz = maxz - minz
      const r = 0.5 * Math.sqrt(sx * sx + sy * sy + sz * sz)
      const targetD = Math.max(60, r * 1.4)
      if (!orbitDist.current) orbitDist.current = targetD
      orbitDist.current += (targetD - orbitDist.current) * 0.08
      const d = orbitDist.current
      orbitAngle.current += 0.012
      const a = orbitAngle.current
      const cam = stage.viewer.camera
      cam.up.set(0, 0, 1)
      cam.position.set(cx + Math.cos(a) * d, cy - Math.sin(a) * d, cz + d * 0.45)
      const look = cam.position.clone().set(cx, cy, cz)
      cam.lookAt(look)
      stage.viewer.requestRender()
      ;(window as any).__cam = { a, d, p: [cam.position.x, cam.position.y, cam.position.z], up: [cam.up.x, cam.up.y, cam.up.z] }
    } catch (_) {
      try { comp.autoView() } catch (_) {}
    }
  }

  const fitCamera = (comp: any, frame: number) => {
    const stage = stageRef.current
    if (!stage || !comp?.structure?.atomStore) return
    try {
      const st = comp.structure.atomStore
      let minx = 1e9, miny = 1e9, minz = 1e9, maxx = -1e9, maxy = -1e9, maxz = -1e9
      for (let i = 0; i < st.count; i++) {
        const x = st.x[i], y = st.y[i], z = st.z[i]
        if (x < minx) minx = x; if (x > maxx) maxx = x
        if (y < miny) miny = y; if (y > maxy) maxy = y
        if (z < minz) minz = z; if (z > maxz) maxz = z
      }
      const cx = (minx + maxx) / 2, cy = (miny + maxy) / 2, cz = (minz + maxz) / 2
      const sx = maxx - minx, sy = maxy - miny, sz = maxz - minz
      const rRaw = 0.5 * Math.sqrt(sx * sx + sy * sy + sz * sz)
      const rs = smoothR.current > 0 ? smoothR.current + (rRaw - smoothR.current) * 0.15 : rRaw
      smoothR.current = rs
      let d = 2.9 * Math.max(rs, rRaw * 0.75)
      const last = lastD.current
      if (last > 0 && Math.abs(d - last) <= 0.4 * last) {
        const step = last * 0.08
        d = Math.min(last + step, Math.max(last - step, d))
      }
      lastD.current = d
      const cam = stage.viewer.camera
      cam.up.set(0, 1, 0)
      cam.position.set(cx, cy, cz - d)
      const look = cam.position.clone().set(cx, cy, cz)
      cam.lookAt(look)
      stage.viewer.requestRender()
    } catch (_) {}
  }

  const updatePivot = () => {}

  const lastPhase = useRef("")
  const smoothC = useRef<{x:number;y:number;z:number;r:number}|null>(null)
  const lastD = useRef(0)
  const smoothR = useRef(0)
  const rHist = useRef<number[]>([])
  const applyFrame = (i: number) => { document.title = 'RUN' + i
    setFrame(i)
    if (!aaN.current) return
    const m = mapDisplay(i)
    if (m.phase !== lastPhase.current) {
      lastPhase.current = m.phase
      compAA.current?.setVisibility(m.phase !== "cg")
      compCG.current?.setVisibility(m.phase === "cg")
    }
    if (m.phase !== "cg") {
      trajAA.current?.setFrame(m.aa!)
      requestAnimationFrame(() => fitCamera(compAA.current, i))
    } else {
      trajCG.current?.setFrame(m.cg!)
      requestAnimationFrame(() => fitCamera(compCG.current, i))
    }
  }

  useEffect(() => {
    document.body.style.margin = "0"
    document.body.style.overflow = "hidden"
    const style = document.createElement("style")
    style.textContent = "header,.header,.app-header,.topbar{display:none!important}"
    document.head.appendChild(style)

    let disposed = false
    async function boot() {
      try {
        const { Stage } = await import("ngl")
        if (disposed || !hostRef.current) return
        const stage = new Stage(hostRef.current, { backgroundColor: "black", tooltip: false, preserveDrawingBuffer: true })
        ;(window as any).__stage = stage
        stageRef.current = stage

        const [cgText, aaText, aaPhaseBuf, aaFoldBuf] = await Promise.all([
          fetch("/api/data/packing/film_topology.pdb").then(r => r.text()),
          fetch("/api/data/packing/aa_fold_topology.pdb").then(r => r.text()),
          fetch("/api/data/packing/aa_phase.dcd").then(r => r.arrayBuffer()),
          fetch("/api/data/packing/aa_fold.dcd").then(r => r.arrayBuffer()),
        ])
        const cgComp = await stage.loadFile(URL.createObjectURL(new Blob([cgText])), { ext: "pdb" })
        compCG.current = cgComp
        repCG.current = cgComp.addRepresentation(REPS.sphere.name, REPS.sphere.params)
        const cgParsed = parseDCD(await fetch("/api/data/packing/film_inplace.dcd").then(r => r.arrayBuffer()))
        cgN.current = cgParsed.nframes
        trajCG.current = cgComp.addTrajectory(makeTrajectoryCallback(cgParsed))
        trajCG.current.setFrame(0)
        cgComp.setVisibility(false)

        const aaComp = await stage.loadFile(URL.createObjectURL(new Blob([aaText])), { ext: "pdb" })
        compAA.current = aaComp
        repAA.current = aaComp.addRepresentation("spacefill", { color: 0xffffff, radiusScale: 0.3 })
        const aaPhase = parseDCD(aaPhaseBuf)
        aaN.current = aaPhase.nframes
        trajAA.current = aaComp.addTrajectory(makeTrajectoryCallback(aaPhase))
        trajAA.current.setFrame(0)
        foldN.current = parseDCD(aaFoldBuf).nframes
        // camera set on first rendered frame

        totalRef.current = displayCount()
        setTotal(totalRef.current)
        setFoldFrames(foldN.current)
        setAaFrames(aaN.current)
        setLoading(false)
        ;(window as any).__film = { total: totalRef.current, setFrame: (i: number) => { frameRef.current = i; applyFrame(i) } }
        ;(window as any).__pivot = updatePivot
        ;(window as any).__filmReady = true
      } catch (e: any) {
        setError(String(e?.stack || e?.message || e)); setLoading(false)
        ;(window as any).__filmError = String(e?.message || e)
      }
    }
    boot()

    const timer = setInterval(() => {
      if (!playingRef.current || !totalRef.current) return
      frameRef.current = (frameRef.current + 1) % totalRef.current
      applyFrame(frameRef.current)
    }, 100)
    return () => { disposed = true; clearInterval(timer) }
  }, [])

  const applyRep = (name: string) => {
    setRepresentation(name)
    if (!compCG.current) return
    if (repCG.current) compCG.current.removeRepresentation(repCG.current)
    const r = REPS[name]
    repCG.current = compCG.current.addRepresentation(r.name, r.params)
  }
  const toggle = () => { playingRef.current = !playingRef.current; setPlaying(playingRef.current); if (!playingRef.current) updatePivot() }
  const seek = (v: number) => { frameRef.current = v; applyFrame(v) }

  return (
    <div style={{ position: "fixed", inset: 0, background: "#fff" }}>
      <div ref={hostRef} style={{ position: "absolute", inset: 0, bottom: 64 }} />
      <div style={{ position: "absolute", left: 20, top: 16, pointerEvents: "none" }}>
        <div style={{ font: "600 15px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif", color: "#1d1d1f" }}>Assembly Trajectory</div>
        <div style={{ font: "12px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif", color: "#6e6e73", marginTop: 3 }}>2KY5 · fold {foldFrames}f + collapse {Math.max(0, Math.ceil((aaFrames - foldFrames) / 4))}f + CG {Math.max(0, total - foldFrames - Math.ceil((aaFrames - foldFrames) / 4))}f · NGL.js</div>
      </div>
      {loading && <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(255,255,255,.55)", font: "14px -apple-system,BlinkMacSystemFont,sans-serif", color: "#6e6e73" }}>Loading trajectory…</div>}
      {error && <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(255,255,255,.9)", font: "12px ui-monospace,monospace", color: "#ff3b30", padding: 24, whiteSpace: "pre-wrap", overflow: "auto" }}>Error: {error}</div>}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 64, display: "flex", alignItems: "center", gap: 14, padding: "0 18px", background: "#f5f5f7", borderTop: "1px solid #e5e5ea", font: "13px -apple-system,BlinkMacSystemFont,sans-serif", color: "#1d1d1f" }}>
        <button onClick={toggle} disabled={loading} style={{ background: playing ? "#ff3b30" : "#0071e3", color: "#fff", border: 0, borderRadius: 8, padding: "8px 18px", font: "600 13px -apple-system,BlinkMacSystemFont,sans-serif", cursor: "pointer", minWidth: 78 }}>{playing ? "Pause" : "Play"}</button>
        <span style={{ color: "#6e6e73", whiteSpace: "nowrap" }}>Frame</span>
        <input type="range" min={0} max={Math.max(0, total - 1)} value={frame} onChange={e => seek(Number(e.target.value))} style={{ flex: 1 }} />
        <span style={{ fontFamily: "ui-monospace,SFMono-Regular,monospace", color: "#6e6e73", minWidth: 84, textAlign: "right" }}>{frame + 1} / {total}</span>
        <select value={representation} onChange={e => applyRep(e.target.value)} style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid #d2d2d7", background: "#fff", color: "#1d1d1f", fontSize: 13 }}>
          <option value="sphere">Sphere</option>
          <option value="stick">Stick</option>
          <option value="line">Line</option>
        </select>
      </div>
    </div>
  )
}
