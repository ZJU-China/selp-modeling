import { useRef, useEffect, useState, useCallback } from "react"
import { useTheme } from "../theme"
import { COLOR, REPLICAS_COLORS } from "../colors"
import { VideoDownloadButtons } from "./VideoDownloadButtons"

interface MolecularViewerProps {
  taskId?: string | null
  replica?: number
  /** When set, shows replica-switching buttons in the section header (the
   *  download buttons sit to their right) and makes the `replica` prop seed
   *  the initial selection. When unset the `replica` prop is fully
   *  controlled by the parent. */
  replicas?: number[]
  /** Optional per-replica display labels (e.g. sample names). When set, the
   *  switching buttons show these instead of "Replica N". */
  replicaLabels?: string[]
  height?: number
  /** When set, loads only the trailing `lastCycles` frames/cycles from the
   *  backend-generated last-N-cycles DCD instead of the preview/full DCD. */
  lastCycles?: number
  /** Fraction of the viewport height the first frame's structure should
   *  initially fill (e.g. ~0.618 for a golden-ratio composition). Smaller
   *  values zoom in further. Uses the current frame's bounding box, so the
   *  first frame is framed directly. */
  zoomRatio?: number
  /** When true, omits this component's own `.section` box and section-header
   *  ("Molecular Dynamics Trajectory") so it can be embedded under a parent
   *  section that already supplies its own title (e.g. TrajectorySection's
   *  "Last N Cycles · Molecular Dynamics Trajectory"). The frame/annotation
   *  legend is still shown. */
  hideHeader?: boolean
}

const REPRESENTATIONS: Record<string, { name: string; params: Record<string, any> }> = {
  cartoon: { name: "cartoon", params: { color: "spectrum" } },
  stick: { name: "ball+stick", params: { color: "jmol" } },
  sphere: { name: "spacefill", params: { color: "jmol", radiusScale: 0.3 } },
  line: { name: "line", params: { color: "jmol" } },
}

export interface ParsedDCD {
  nframes: number
  natoms: number
  delta: number
  coordinates: Float32Array[]
  boxes: (Float32Array | null)[]
}

interface SequenceOccurrence {
  chain: string
  start: number
  end: number
}

interface SequenceAnnotation {
  sequence: string
  label: string
  color: string
  occurrences: SequenceOccurrence[]
}

export function parseDCD(buffer: ArrayBuffer): ParsedDCD {
  const data = new DataView(buffer)
  const isLittleEndian = true

  const magic = data.getInt32(0, isLittleEndian)
  if (magic !== 84) {
    throw new Error(`DCD: bad magic number ${magic}, expected 84`)
  }

  const cord = String.fromCharCode(data.getUint8(4), data.getUint8(5), data.getUint8(6), data.getUint8(7))
  if (cord !== "CORD") {
    throw new Error(`DCD: bad format string "${cord}", expected "CORD"`)
  }

  const nset = data.getInt32(8, isLittleEndian)
  const delta = data.getFloat64(44, isLittleEndian)

  let offset = 92

  const titleBlockLen = data.getInt32(offset, isLittleEndian)
  offset += 4 + titleBlockLen + 4

  offset += 4
  const natoms = data.getInt32(offset, isLittleEndian)
  offset += 4 + 4

  const p4 = 4 * natoms
  const coordinates: Float32Array[] = []
  const boxes: (Float32Array | null)[] = []

  for (let i = 0; i < nset; i++) {
    const blockStart = data.getInt32(offset, isLittleEndian)
    if (blockStart === 48) {
      offset += 4
      const box = new Float32Array(9)
      box[0] = data.getFloat64(offset, isLittleEndian) as any
      box[4] = data.getFloat64(offset + 16, isLittleEndian) as any
      box[8] = data.getFloat64(offset + 40, isLittleEndian) as any
      boxes.push(box)
      offset += 48
      const blockEnd = data.getInt32(offset, isLittleEndian)
      offset += 4
      if (blockEnd !== 48) {
        offset -= 4
      }
    } else {
      boxes.push(null)
    }

    // Fast path: reinterpret the per-dimension float blocks directly as
    // Float32Array views (byte offset stays 4-aligned for standard DCDs),
    // then interleave into xyz order. Falls back to DataView on misalignment.
    const coords = new Float32Array(3 * natoms)
    for (let dim = 0; dim < 3; dim++) {
      const coordBlockLen = data.getInt32(offset, isLittleEndian)
      offset += 4
      if (offset % 4 === 0) {
        const raw = new Float32Array(buffer, offset, natoms)
        for (let a = 0; a < natoms; a++) {
          coords[3 * a + dim] = raw[a]
        }
      } else {
        for (let a = 0; a < natoms; a++) {
          coords[3 * a + dim] = data.getFloat32(offset + a * 4, isLittleEndian)
        }
      }
      offset += p4
      const coordBlockEnd = data.getInt32(offset, isLittleEndian)
      offset += 4
      if (coordBlockEnd !== coordBlockLen) {
        offset -= 4
      }
    }
    coordinates.push(coords)
  }

  return { nframes: nset, natoms, delta, coordinates, boxes }
}

// Fetch a binary file with a download progress callback (streams when the
// browser supports it, otherwise falls back to a single arrayBuffer()).
async function fetchBuffer(url: string, onProgress: (pct: number) => void): Promise<ArrayBuffer> {
  const response = await fetch(url)
  if (!response.ok) throw new Error(`DCD fetch failed (${response.status})`)

  const total = Number(response.headers.get("Content-Length") || 0)
  if (!response.body || !total) {
    const buf = await response.arrayBuffer()
    onProgress(100)
    return buf
  }

  const reader = response.body.getReader()
  const chunks: Uint8Array[] = []
  let received = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    received += value.length
    onProgress(Math.min(99, Math.round((received / total) * 100)))
  }

  const merged = new Uint8Array(received)
  let pos = 0
  for (const chunk of chunks) {
    merged.set(chunk, pos)
    pos += chunk.length
  }
  onProgress(100)
  return merged.buffer as ArrayBuffer
}

export function makeTrajectoryCallback(parsed: ParsedDCD) {
  return function requestCallback(
    innerFn: any,
    frameIndexOrUndefined?: number,
    _atomIndices?: any
  ) {
    if (frameIndexOrUndefined === undefined) {
      innerFn(parsed.nframes)
    } else {
      const idx = Math.min(frameIndexOrUndefined, parsed.nframes - 1)
      innerFn(frameIndexOrUndefined, parsed.boxes[idx] || null, parsed.coordinates[idx], parsed.nframes)
    }
  }
}

// Position the camera so the structure's largest extent fills `ratio` of the
// viewport height. NGL's perspective projection maps maxExtent to exactly
// ratio * height when distance = maxExtent / (2 * tan(fov / 2) * ratio).
function zoomToRatio(stage: any, component: any, ratio: number) {
  const box = component.getBox()
  if (!box || !box.min || !box.max) return
  const maxExtent = Math.max(
    box.max.x - box.min.x,
    box.max.y - box.min.y,
    box.max.z - box.min.z,
  )
  if (!isFinite(maxExtent) || maxExtent <= 0) return
  const center = {
    x: (box.max.x + box.min.x) / 2,
    y: (box.max.y + box.min.y) / 2,
    z: (box.max.z + box.min.z) / 2,
  }
  const fov = (stage.viewer.perspectiveCamera?.fov ?? 40) * Math.PI / 180
  const width = stage.viewer.width ?? 800
  const height = stage.viewer.height ?? 400
  const fittedRatio = width < height ? ratio * (width / height) : ratio
  const distance = maxExtent / (2 * Math.tan(fov / 2) * fittedRatio)
  if (!isFinite(distance) || distance <= 0) return
  stage.animationControls.zoomMove(center, -distance, 0)
}

// Geometric center (bounding-box midpoint) of one parsed trajectory frame.
function frameBoxCenter(coords: Float32Array) {
  let minX = Infinity, minY = Infinity, minZ = Infinity
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity
  for (let i = 0; i < coords.length; i += 3) {
    const x = coords[i], y = coords[i + 1], z = coords[i + 2]
    if (x < minX) minX = x
    if (y < minY) minY = y
    if (z < minZ) minZ = z
    if (x > maxX) maxX = x
    if (y > maxY) maxY = y
    if (z > maxZ) maxZ = z
  }
  return { x: (minX + maxX) / 2, y: (minY + maxY) / 2, z: (minZ + maxZ) / 2 }
}

export function MolecularViewer({ taskId, replica = 0, replicas, replicaLabels, height = 500, lastCycles, zoomRatio, hideHeader = false }: MolecularViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<any>(null)
  const structCompRef = useRef<any>(null)
  const trajElemRef = useRef<any>(null)
  const playerRef = useRef<any>(null)
  const parsedDCDRef = useRef<ParsedDCD | null>(null)
  const annotationsRef = useRef<SequenceAnnotation[]>([])

  const [internalReplica, setInternalReplica] = useState(replica)
  // Self-managed when the section shows its own replica buttons; otherwise
  // fully controlled by the parent via the `replica` prop.
  const activeReplica = replicas ? internalReplica : replica
  const replicaColors = replicas ? REPLICAS_COLORS(replicas.length) : []

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [currentFrame, setCurrentFrame] = useState(0)
  const [totalFrames, setTotalFrames] = useState(0)
  const [representation, setRepresentation] = useState<"cartoon" | "stick" | "sphere" | "line">("cartoon")
  const [speed, setSpeed] = useState(10)
  const [syncStatus, setSyncStatus] = useState<any>(null)
  const [annotations, setAnnotations] = useState<SequenceAnnotation[]>([])
  const [totalResidues, setTotalResidues] = useState<number | null>(null)
  const [trajectoryMode, setTrajectoryMode] = useState<"preview" | "full">("preview")
  const [downloadProgress, setDownloadProgress] = useState<number | null>(null)
  const { resolved: theme } = useTheme()
  const isDark = theme === "dark"

  const pdbUrl = taskId ? `/api/data/pdb?taskId=${taskId}` : null
  const previewDcdUrl = taskId ? `/api/data/dcd-preview/${taskId}_rep${activeReplica}.dcd` : null
  const fullDcdUrl = taskId ? `/api/data/dcd-file/${taskId}_rep${activeReplica}.dcd` : null
  const tailDcdUrl = taskId && lastCycles ? `/api/data/dcd-last100/${taskId}_rep${activeReplica}.dcd` : null

  // Highlight every occurrence of each annotated sequence on the loaded
  // structure. Annotations use the same representation as the structure theme
  // (cartoon/stick/sphere/line), so changing the tab keeps everything unified;
  // each sequence keeps its own CSV color for distinction. Selections are
  // structure-based, so they persist over frames.
  const applyAnnotations = useCallback(() => {
    const structureComponent = structCompRef.current
    if (!structureComponent) return
    const repr = REPRESENTATIONS[representation]
    annotationsRef.current.forEach(ann => {
      // NGL 2.4 (the bundled build) does not understand the keyword syntax
      // "chain A and resid 1-12" (it fails to parse and silently selects
      // every atom, turning the whole molecule into one color). Use the
      // compact "resno:chain" form, which parses and filters correctly.
      const parts = ann.occurrences.map(o => {
        const chainSel = (o.chain || "").trim()
        return chainSel ? `${o.start}-${o.end}:${chainSel}` : `${o.start}-${o.end}`
      })
      if (!parts.length) return
      const sele = parts.join(" or ")
      try {
        structureComponent.addRepresentation(repr.name, {
          ...repr.params,
          sele,
          color: ann.color,
        })
      } catch (e) {
        console.error(`[MolecularViewer] failed to annotate "${ann.label}":`, e)
      }
    })
  }, [representation])

  const loadTrajectory = useCallback(async () => {
    const stage = stageRef.current
    if (!stage || !pdbUrl) return

    try {
      setLoading(true)
      setError(null)

      if (playerRef.current) {
        playerRef.current.pause()
        playerRef.current = null
      }
      if (structCompRef.current) {
        stage.removeAllComponents()
        structCompRef.current = null
        trajElemRef.current = null
      }

      const ngl = await import("ngl")
      const { TrajectoryPlayer, Stage: _Stage } = ngl

      const structureComponent = await stage.loadFile(pdbUrl, { ext: "pdb" })
      if (!structureComponent) throw new Error("Failed to load PDB structure")
      structCompRef.current = structureComponent

      const repr = REPRESENTATIONS[representation]
      const params = { ...repr.params }
      if (repr.name === "cartoon") {
        params.color = isDark ? COLOR.white : COLOR.cartoonLight
      }
      structureComponent.addRepresentation(repr.name, params)

      applyAnnotations()

      const usePreview = trajectoryMode === "preview" && !lastCycles
      const trajectoryUrl = lastCycles ? tailDcdUrl : (usePreview && previewDcdUrl ? previewDcdUrl : fullDcdUrl)
      if (trajectoryUrl) {
        setDownloadProgress(0)
        let buffer: ArrayBuffer
        try {
          buffer = await fetchBuffer(trajectoryUrl, setDownloadProgress)
        } catch (e) {
          // Tail/preview not yet synced: fall back to the full merged DCD.
          if (fullDcdUrl && trajectoryUrl !== fullDcdUrl) {
            buffer = await fetchBuffer(fullDcdUrl, setDownloadProgress)
          } else {
            throw e
          }
        }
        setDownloadProgress(null)
        if (buffer.byteLength === 0) throw new Error("DCD file is empty")

        const parsed = parseDCD(buffer)
        parsedDCDRef.current = parsed

        if (parsed.nframes === 0) throw new Error("DCD file contains no frames")
        if (parsed.natoms === 0) throw new Error("DCD file contains no atoms")

        const callbackFn = makeTrajectoryCallback(parsed)
        const trajElem = structureComponent.addTrajectory(callbackFn as any)
        if (!trajElem) throw new Error("Failed to add trajectory to structure")

        const traj = trajElem.trajectory
        if (!traj) throw new Error("TrajectoryElement has no .trajectory property")
        trajElemRef.current = trajElem

        traj.signals.frameChanged.add((i: number) => {
          setCurrentFrame(i)
          const parsed = parsedDCDRef.current
          if (parsed && parsed.coordinates[i]) {
            try {
              stage.viewerControls.center(frameBoxCenter(parsed.coordinates[i]))
            } catch (_) {}
          }
        })

        traj.signals.countChanged.add((count: number) => {
          setTotalFrames(count)
        })

        setTotalFrames(parsed.nframes)

        const player = new TrajectoryPlayer(traj, {
          step: 1,
          timeout: 1000 / speed,
          mode: "loop" as const,
          direction: "forward" as const,
        })
        playerRef.current = player

        // Set frame 0 to display DCD coordinates instead of PDB default
        trajElem.setFrame(0)
        setCurrentFrame(0)
      } else {
        setTotalFrames(1)
      }

      try {
        if (zoomRatio) {
          zoomToRatio(stage, structureComponent, zoomRatio)
        } else {
          stage.autoView()
        }
      } catch (_) { /* WebGL may not be available */ }
      setLoading(false)
    } catch (e: any) {
      console.error("[MolecularViewer] load error:", e)
      setError(e.message || "Failed to load trajectory")
      setLoading(false)
      setDownloadProgress(null)
    }
  }, [pdbUrl, previewDcdUrl, fullDcdUrl, tailDcdUrl, representation, activeReplica, trajectoryMode, lastCycles, zoomRatio, applyAnnotations])

  useEffect(() => {
    if (!containerRef.current) return
    let disposed = false

    import("ngl").then(({ Stage }) => {
      if (disposed || !containerRef.current) return
      const stage = new Stage(containerRef.current!, {
        backgroundColor: isDark ? COLOR.nglBgDark : COLOR.white,
      })
      stageRef.current = stage
      loadTrajectory()
    }).catch((e) => {
      console.error("[MolecularViewer] NGL import error:", e)
      setError("Failed to load NGL.js: " + e.message)
      setLoading(false)
    })

    return () => {
      disposed = true
      if (playerRef.current) {
        playerRef.current.pause()
      }
      if (stageRef.current) {
        stageRef.current.dispose()
        stageRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    loadTrajectory()
  }, [pdbUrl, previewDcdUrl, fullDcdUrl, tailDcdUrl, activeReplica, trajectoryMode, lastCycles, zoomRatio])

  useEffect(() => {
    if (!stageRef.current || !structCompRef.current) return
    loadTrajectory()
  }, [representation])

  useEffect(() => {
    if (playerRef.current) {
      playerRef.current.setParameters({ timeout: 1000 / speed })
    }
  }, [speed])

  useEffect(() => {
    if (!taskId) return
    const statusUrl = `/api/data/trajectory-status?taskId=${taskId}`

    const poll = setInterval(() => {
      fetch(statusUrl)
        .then(r => r.json())
        .then(setSyncStatus)
        .catch(() => {})
    }, 30000)

    fetch(statusUrl)
      .then(r => r.json())
      .then(setSyncStatus)
      .catch(() => {})

    return () => clearInterval(poll)
  }, [taskId])

  useEffect(() => {
    if (!taskId) return
    let cancelled = false
    fetch(`/api/data/sequence-annotations?taskId=${taskId}`)
      .then(r => r.json())
      .then(d => {
        if (cancelled) return
        const list: SequenceAnnotation[] = d?.annotations || []
        annotationsRef.current = list
        setAnnotations(list)
        setTotalResidues(d?.totalResidues ?? null)
        applyAnnotations()
      })
      .catch((e) => console.error("[MolecularViewer] annotations fetch failed:", e))
    return () => { cancelled = true }
  }, [taskId])

  useEffect(() => {
    if (stageRef.current) {
      stageRef.current.setParameters({
        backgroundColor: isDark ? COLOR.nglBgDark : COLOR.white,
      })
    }
  }, [isDark])

  const togglePlayback = () => {
    if (!playerRef.current) return

    if (playing) {
      playerRef.current.pause()
    } else {
      playerRef.current.play()
    }
    setPlaying(!playing)
  }

  const goToFrame = (frame: number) => {
    if (!trajElemRef.current) return
    trajElemRef.current.setFrame(frame)
    setCurrentFrame(frame)
  }

  const handleFrameSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPlaying(false)
    if (playerRef.current) playerRef.current.pause()
    goToFrame(Number(e.target.value))
  }

  const syncNow = async () => {
    if (!taskId) return
    try {
      await fetch(`/api/data/trajectory-sync?taskId=${taskId}`, { method: "POST" })
      loadTrajectory()
    } catch (e) {
      console.error("Sync failed:", e)
    }
  }

  const legend = (
    <div className="legend" style={{ flexWrap: "nowrap" }}>
      <div className="legend-item" style={{ fontSize: 13, color: COLOR.muted }}>
        2KY10 SELP · {totalFrames} frames{lastCycles ? ` · last ${lastCycles} cycles` : (trajectoryMode === "preview" ? " (preview)" : "")} · NGL.js
      </div>
      {annotations.map(ann => (
        <div className="legend-item" key={ann.sequence} title={`${ann.sequence} · ${ann.occurrences.length} occurrence(s)`}>
          <span style={{
            display: "inline-block", width: 10, height: 10, borderRadius: 3,
            background: ann.color, marginRight: 6, verticalAlign: "middle",
          }} />
          <span style={{ fontSize: 12, color: COLOR.muted, verticalAlign: "middle" }}>
            {ann.label} × {ann.occurrences.length}
          </span>
        </div>
      ))}
    </div>
  )

  const body = (
    <>
      <div style={{
        position: "relative",
        borderRadius: "var(--radius-md)",
        overflow: "hidden",
        border: "1px solid var(--hairline)",
      }}>
        <div
          ref={containerRef}
          style={{ width: "100%", height: `${height}px`, position: "relative" }}
        />

        {loading && (
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "rgba(0,0,0,0.5)", color: "white", fontSize: 14, zIndex: 10,
          }}>
            {downloadProgress !== null
              ? `Downloading trajectory... ${downloadProgress}%`
              : "Loading trajectory..."}
          </div>
        )}

        {error && (
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
            background: "rgba(0,0,0,0.5)", color: COLOR.danger, fontSize: 14, padding: 20, textAlign: "center", zIndex: 10,
          }}>
            <div>Error: {error}</div>
            <button
              onClick={syncNow}
              style={{
                marginTop: 12, padding: "8px 16px", background: COLOR.accent, color: COLOR.white,
                border: "none", borderRadius: 8, cursor: "pointer", fontSize: 13,
              }}
            >
              Sync from Server
            </button>
          </div>
        )}
      </div>

      <div style={{
        display: "flex", alignItems: "center", gap: 16, marginTop: 16,
        padding: "12px 16px", background: "var(--canvas-parchment)", borderRadius: "var(--radius-sm)",
      }}>
        <button
          onClick={togglePlayback}
          disabled={loading || totalFrames <= 1}
          style={{
            background: playing ? COLOR.danger : COLOR.accent, color: COLOR.white, border: "none",
            borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600,
            cursor: loading || totalFrames <= 1 ? "not-allowed" : "pointer",
            minWidth: 80, opacity: loading || totalFrames <= 1 ? 0.5 : 1,
          }}
        >
          {playing ? "Pause" : "Play"}
        </button>

        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, color: COLOR.muted, whiteSpace: "nowrap" }}>Frame</span>
          <input
            type="range"
            min={0}
            max={Math.max(0, totalFrames - 1)}
            value={currentFrame}
            onChange={handleFrameSliderChange}
            disabled={totalFrames <= 1}
            style={{ flex: 1 }}
          />
          <span style={{ fontSize: 12, color: COLOR.muted, fontFamily: "var(--font-mono)", minWidth: 60 }}>
            {currentFrame + 1} / {totalFrames}
          </span>
        </div>

        <select
          value={representation}
          onChange={(e) => setRepresentation(e.target.value as typeof representation)}
          style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--hairline)", fontSize: 13, background: "var(--canvas)", color: "var(--body)", cursor: "pointer" }}
        >
          <option value="cartoon">Cartoon</option>
          <option value="stick">Stick</option>
          <option value="sphere">Sphere</option>
          <option value="line">Line</option>
        </select>

        {!lastCycles && (
          <select
            value={trajectoryMode}
            onChange={(e) => setTrajectoryMode(e.target.value as typeof trajectoryMode)}
            style={{ padding: "6px 10px", borderRadius: 6, border: "1px solid var(--hairline)", fontSize: 13, background: "var(--canvas)", color: "var(--body)", cursor: "pointer" }}
            title="Preview loads a downsampled trajectory for fast display; Full loads every frame"
          >
            <option value="preview">Preview (fast)</option>
            <option value="full">Full trajectory</option>
          </select>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 12, color: COLOR.muted }}>Speed</span>
          <input
            type="range"
            min={1}
            max={60}
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            style={{ width: 80 }}
          />
          <span style={{ fontSize: 12, color: COLOR.muted, fontFamily: "var(--font-mono)", minWidth: 30 }}>
            {speed}fps
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginTop: 16 }}>
        <div className="stat-card" style={{ padding: 12 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--primary)" }}>{totalResidues ?? 750} aa</div>
          <div className="stat-label" style={{ fontSize: 11 }}>Residues</div>
        </div>
        <div className="stat-card" style={{ padding: 12 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--primary)" }}>{totalFrames}</div>
          <div className="stat-label" style={{ fontSize: 11 }}>Frames</div>
        </div>
        <div className="stat-card" style={{ padding: 12 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--primary)" }}>4.0 fs</div>
          <div className="stat-label" style={{ fontSize: 11 }}>Timestep</div>
        </div>
        <div className="stat-card" style={{ padding: 12 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "var(--primary)" }}>CHARMM36m</div>
          <div className="stat-label" style={{ fontSize: 11 }}>Force Field</div>
        </div>
      </div>

      {syncStatus && (
        <div style={{
          marginTop: 16, padding: "8px 12px", fontSize: 12, color: COLOR.muted,
          background: "var(--canvas-parchment)", borderRadius: "var(--radius-sm)",
          display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap",
        }}>
          <span>
            Last sync: {syncStatus.generatedAt ? new Date(syncStatus.generatedAt).toLocaleTimeString() : "Never"} ·
            Size: {((syncStatus.pdbSize || 0) + (syncStatus.dcdSize || 0)) / 1024 / 1024} MB
          </span>
          <button
            onClick={syncNow}
            style={{
              padding: "4px 12px", fontSize: 12, background: "transparent",
              color: COLOR.accent, border: "1px solid var(--hairline)", borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Sync Now
          </button>
        </div>
      )}
    </>
  )

  return hideHeader ? (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>{legend}</div>
      {body}
    </div>
  ) : (
    <div className="section">
      <div className="section-header">
        <h3 className="section-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
            <path d="M2 17l10 5 10-5"/>
            <path d="M2 12l10 5 10-5"/>
          </svg>
          Molecular Dynamics Trajectory
        </h3>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", justifyContent: "flex-end" }}>
          {legend}
          {replicas && (
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "nowrap" }}>
                  <span style={{ fontSize: 13, color: COLOR.muted }}>Replica:</span>
                  {replicas.map(rep => (
                    <button
                      key={rep}
                      onClick={() => setInternalReplica(rep)}
                      style={{
                        padding: "6px 14px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600,
                        cursor: "pointer", transition: "all 0.15s",
                        background: activeReplica === rep ? replicaColors[rep] : "transparent",
                        color: activeReplica === rep ? "white" : replicaColors[rep],
                        outline: activeReplica === rep ? "none" : `1px solid ${replicaColors[rep]}`,
                      }}
                    >
                      {replicaLabels && replicaLabels[rep] ? replicaLabels[rep] : `Replica ${rep}`}
                    </button>
                  ))}
            </div>
          )}
          {taskId && <VideoDownloadButtons taskId={taskId} replica={activeReplica} full />}
        </div>
      </div>
      {body}
    </div>
  )
}
