import { readFile, writeFile, mkdir, rm, readdir, rename, open } from "fs/promises"
import { existsSync } from "fs"
import { join } from "path"
import { createHash } from "crypto"
import { spawn, execFile } from "child_process"
import { promisify } from "util"
import { getTrajectoryCacheDir, getPDBData, syncTrajectoryFiles } from "./trajectory-sync.js"
import { runMain } from "./run-main.js"

const execFileP = promisify(execFile)
const HOME = process.env.HOME || "/home/selp"
// Interpreter override for the conda env that carries imageio-ffmpeg (bundles
// a static ffmpeg binary). VMD renders the TGA frames; ffmpeg encodes MP4.
const PYTHON_BIN = process.env.MD_PYTHON_BIN || join(HOME, ".local", "miniconda3", "envs", "igem2026", "bin", "python3")
const VMD_BIN = process.env.MD_VMD_BIN || "vmd"

// TachyonInternal degrades in long single VMD sessions (it stalls after ~80
// renders), so frames are rendered in small chunks with a fresh VMD per chunk.
const CHUNK_SIZE = 20
const WATCHDOG_MS = 90000

// In -dispdev text mode `vmd -size 800 600` renders 800x608 frames (the width
// is honored, the height lands 8px over), on a black backdrop. VMD pins an
// xyz-axis trihedron at the lower-left of every frame (x 103-184, y 446-531);
// `axes location Off` kills it outright, so the pipelines need no drawbox and
// (important) the reference `display resetview` fit no longer includes the
// trihedron in the scene bounds — with it on, the resetview fit in headless
// mode lands the molecule ~40px low and anisotropically stretched; with it
// off, the origin-centered molecule renders dead-center and near-isotropic.
// Framing: the camera is fitted ONCE to a reference view — frame 0, centered
// on its outlier-trimmed bounding-box midpoint and uniformly scaled to 100 A —
// via `display resetview`, using orthographic projection (`display perspective
// off` is a no-op headless; `display projection Orthographic` is the switch
// that stops the per-frame center drift). Every frame is then re-centered on
// its trimmed bbox midpoint and uniformly scaled so its longest bounding-box
// axis equals MOL_EXTENT Angstroms; with the fixed orthographic camera that
// maps linearly to the rendered extent. MOL_EXTENT=133 lands the mean rendered
// extent at ~0.618 of the frame height (measured across tail and full
// trajectories), matching the golden ratio the MD preview uses (zoomToRatio:
// maxExtent / height = 1 / 1.618). Extent still drifts a few percent frame to
// frame because the molecule itself changes shape (the preview, which re-frames
// per frame, hides this).
const MOL_EXTENT = 133

// Cartoon styling shared by the base and annotation reps. Centralized so the
// render-signature (below) hashes exactly what the frames were drawn with.
const RIBBON_THICKNESS = 1.0
const RIBBON_ASPECT_RATIO = 10
const RIBBON_BASE_RGB = "0.9098 0.9098 0.9098"
const FPS = 24
const WIDTH = 1280
const HEIGHT = 720
const MAX_FRAMES = 200

const jobs = new Map()
let ffmpegBin = null

const jobKey = (taskId, replica, full, format) => `${taskId}:${replica}:${full ? "full" : "tail"}:${format}`
const downloadUrl = (taskId, replica, full, format) =>
  `/api/video/download?taskId=${encodeURIComponent(taskId)}&replica=${replica}${full ? "&full=1" : ""}${format === "gif" ? "&format=gif" : ""}`
const fileName = (replica, full, format) => `replica_${replica}${full ? "_full" : ""}.${format === "gif" ? "gif" : "mp4"}`

async function getFFmpegBin() {
  if (ffmpegBin) return ffmpegBin
  const { stdout } = await execFileP(PYTHON_BIN, ["-c", "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"])
  ffmpegBin = stdout.trim()
  if (!ffmpegBin) throw new Error("Could not resolve ffmpeg (imageio-ffmpeg)")
  return ffmpegBin
}

export async function getVideoFile(taskId, replica, full = false, format = "mp4") {
  const cacheDir = await getTrajectoryCacheDir(taskId)
  const p = join(cacheDir, "video", fileName(replica, full, format))
  return existsSync(p) ? p : null
}

// A hash of everything that shapes the rendered frames (the renderer source
// itself plus every setting fed into it). Cached MP4/GIFs carry a `.sig`
// sidecar; whenever this hash differs from the sidecar the cached render is
// stale and a download re-renders with the current code.
async function renderSignature(full, format, annotations) {
  const src = await readFile(new URL(import.meta.url))
  const codeHash = createHash("sha256").update(src).digest("hex").slice(0, 16)
  const normalized = (annotations || [])
    .filter(a => a.color && Array.isArray(a.occurrences) && a.occurrences.length)
    .map(a => ({
      color: a.color,
      occurrences: a.occurrences
        .map(o => ({ chain: o.chain ?? null, start: o.start, end: o.end }))
        .sort((x, y) => x.start - y.start || String(x.chain || "").localeCompare(String(y.chain || ""))),
    }))
    .sort((x, y) => String(x.color).localeCompare(String(y.color)))
  const cfg = JSON.stringify({
    codeHash,
    full,
    format,
    fps: FPS,
    width: WIDTH,
    height: HEIGHT,
    maxFrames: MAX_FRAMES,
    extent: MOL_EXTENT,
    thickness: RIBBON_THICKNESS,
    aspect: RIBBON_ASPECT_RATIO,
    baseRgb: RIBBON_BASE_RGB,
    annotations: normalized,
  })
  return createHash("sha256").update(cfg).digest("hex")
}

const videoPaths = async (taskId, replica, full, format) => {
  const outDir = join(await getTrajectoryCacheDir(taskId), "video")
  const finalPath = join(outDir, fileName(replica, full, format))
  return { outDir, finalPath, sigPath: `${finalPath}.sig` }
}

export async function isVideoFresh(taskId, replica, full, format) {
  const { finalPath, sigPath } = await videoPaths(taskId, replica, full, format)
  if (!existsSync(finalPath)) return false
  const annotations = await getAnnotations(taskId)
  const signature = await renderSignature(full, format, annotations)
  try {
    return (await readFile(sigPath, "utf8")).trim() === signature
  } catch {
    return false
  }
}

export async function getVideoStatus(taskId, replica, full = false, format = "mp4") {
  const job = jobs.get(jobKey(taskId, replica, full, format))
  if (job) {
    if (job.status === "done") return { status: "done", url: downloadUrl(taskId, replica, full, format) }
    return { status: job.status, progress: job.progress, error: job.error || undefined }
  }
  const file = await getVideoFile(taskId, replica, full, format)
  if (file) {
    // Cached render exists, but only hand it out if it matches the current
    // code/settings; otherwise kick off a fresh render.
    if (await isVideoFresh(taskId, replica, full, format)) {
      return { status: "done", url: downloadUrl(taskId, replica, full, format) }
    }
    return startVideoRender(taskId, replica, { full, format })
  }
  return { status: "idle" }
}

export async function startVideoRender(taskId, replica, opts = {}) {
  const full = !!opts.full
  const format = opts.format === "gif" ? "gif" : "mp4"

  // Every download re-renders from scratch: the cached file is deleted up
  // front, so the frontend never gets an instant (possibly stale) result.
  // Concurrent requests for the same target dedupe on the in-flight job.
  const { finalPath, sigPath } = await videoPaths(taskId, replica, full, format)
  await rm(finalPath, { force: true })
  await rm(sigPath, { force: true })

  const k = jobKey(taskId, replica, full, format)
  const running = jobs.get(k)
  if (running && running.status === "rendering") return { status: "rendering", progress: running.progress }
  if (running && running.status === "error") jobs.delete(k)

  const annotations = await getAnnotations(taskId)
  const signature = await renderSignature(full, format, annotations)
  const job = { status: "rendering", progress: 0, startedAt: Date.now() }
  jobs.set(k, job)
  renderVideo(taskId, replica, job, { ...opts, annotations, signature }).catch(e => {
    job.status = "error"
    job.error = e.message || String(e)
    console.error(`[TrajectoryVideo] ${taskId} rep${replica}${full ? " full" : ""} ${format} render failed: ${job.error}`)
  })
  return { status: "rendering", progress: 0 }
}

// Read NSET (frame count) straight from the DCD header.
async function readDCDNframes(filePath) {
  const fd = await open(filePath, "r")
  try {
    const buf = Buffer.alloc(12)
    await fd.read(buf, 0, 12, 0)
    return buf.readInt32LE(8)
  } finally {
    await fd.close()
  }
}

const hexToRgb = hex => {
  const m = /^#?([0-9a-fA-F]{6})$/.exec(String(hex || ""))
  if (!m) return null
  const n = parseInt(m[1], 16)
  return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255].map(v => v.toFixed(4))
}

// Sequence annotations exactly as the MD Trajectory viewer legend shows them
// (from the task's input/sequences.csv): used to color highlighted segments.
async function getAnnotations(taskId) {
  try {
    const result = await runMain(taskId, "route", ["--route", "sequences"], { timeout: 30000 })
    if (result && Array.isArray(result.annotations)) return result.annotations
  } catch (e) {
    console.warn(`[TrajectoryVideo] ${taskId}: annotations unavailable (${e.message})`)
  }
  return []
}

async function framesProgress(workDir, expected) {
  try {
    const files = (await readdir(workDir)).filter(f => f.endsWith(".tga")).length
    return Math.min(99, Math.round((files / Math.max(1, expected)) * 100))
  } catch {
    return 0
  }
}

// Render one contiguous range of frames with a single (fresh) VMD process.
async function renderChunk(job, dcdPath, pdbPath, workDir, step, startIdx, endIdx, expected, annotations = []) {
  const framePattern = join(workDir, "frame_%05d.tga")
  const annotated = annotations.filter(a => a.color && Array.isArray(a.occurrences) && a.occurrences.length)
  // Every residue range that carries an annotation color, as a VMD selection.
  const annSelections = annotated.flatMap(a => a.occurrences).map(
    o => (o.chain ? `(resid ${o.start} to ${o.end} and chain ${o.chain})` : `(resid ${o.start} to ${o.end})`)
  )
  const lines = [
    // Flat black backdrop, no shadows/depth cues. Orthographic projection: in
    // headless text mode VMD's default perspective view lets the frame center
    // drift; this pins it so per-frame centering lands exactly on the screen
    // center.
    "display backgroundgradient off",
    "color Display Background black",
    "display depthcue off",
    "display shadows off",
    "display ambientocclusion off",
    "display projection Orthographic",
    // The lower-left xyz trihedron must go: besides cluttering the frame it
    // pollutes the reference `display resetview` fit below (shifts the
    // molecule ~40px low and stretches the projection).
    "axes location Off",
    `mol new ${pdbPath}`,
    "animate delete all",
    `mol addfile ${dcdPath} first 0 last -1 step ${step} waitfor all`,
    "mol delrep 0 top",
    // Base cartoon in the same light gray as the preview (#e8e8e8). Thickness
    // 1.0 Å matches the NGL preview's ribbon (its cartoon tube/strand width is
    // ~0.7-1.75 Å), clearly thicker than VMD's 0.3 default.
    `color change rgb 30 ${RIBBON_BASE_RGB}`,
    `mol representation NewCartoon ${RIBBON_THICKNESS} ${RIBBON_ASPECT_RATIO}`,
    "mol color ColorID 30",
    // The base rep must NOT draw the annotated residues: the annotation reps
    // below draw the exact same NewCartoon geometry there, and two coincident
    // surfaces z-fight into a speckled red/green-gray mosaic. Disjoint
    // selections render each region in its own pure color.
    `mol selection {${annSelections.length ? `all and not (${annSelections.join(" or ")})` : "all"}}`,
    "mol addrep top",
  ]
  annotated.forEach((ann, i) => {
    const rgb = hexToRgb(ann.color) || [1, 0.5, 0]
    const cid = 31 + i
    lines.push(`color change rgb ${cid} ${rgb.join(" ")}`)
    const sel = ann.occurrences
      .map(o => (o.chain ? `(resid ${o.start} to ${o.end} and chain ${o.chain})` : `(resid ${o.start} to ${o.end})`))
      .join(" or ")
    lines.push(`mol representation NewCartoon ${RIBBON_THICKNESS} ${RIBBON_ASPECT_RATIO}`)
    lines.push(`mol color ColorID ${cid}`)
    lines.push(`mol selection {${sel}}`)
    lines.push("mol addrep top")
  })
  // Trimmed bounding box (drop the outermost 1% of atoms per axis) so stray
  // outlier atoms in a frame can't skew the centering or the extent.
  lines.push("proc robustbb {sel} {")
  lines.push("  set xs [$sel get x]")
  lines.push("  set ys [$sel get y]")
  lines.push("  set zs [$sel get z]")
  lines.push("  set xs [lsort -real $xs]")
  lines.push("  set ys [lsort -real $ys]")
  lines.push("  set zs [lsort -real $zs]")
  lines.push("  set n [llength $xs]")
  lines.push("  set trim [expr {int($n * 0.01)}]")
  lines.push("  set lo [list [lindex $xs $trim] [lindex $ys $trim] [lindex $zs $trim]]")
  lines.push("  set hi [list [lindex $xs [expr {$n - 1 - $trim}]] [lindex $ys [expr {$n - 1 - $trim}]] [lindex $zs [expr {$n - 1 - $trim}]]]")
  lines.push("  return [list $lo $hi]")
  lines.push("}")
  // Fit the camera ONCE to a fixed 100 A reference (frame 0, centered on its
  // trimmed bbox midpoint and scaled to 100 A). Every render chunk loads the
  // same DCD, so this yields the identical orthographic view/zoom in each
  // chunk; the per-frame scaling below then maps linearly to the extent.
  lines.push("animate goto 0")
  lines.push("set s0 [atomselect top all]")
  lines.push("set mm0 [robustbb $s0]")
  lines.push("set lo0 [lindex $mm0 0]")
  lines.push("set hi0 [lindex $mm0 1]")
  lines.push("$s0 moveby [vecscale -1 [vecadd $lo0 [vecscale 0.5 [vecsub $hi0 $lo0]]]]")
  lines.push("set dv0 [vecsub $hi0 $lo0]")
  lines.push("set ax0 [expr {[lindex $dv0 0] > [lindex $dv0 1] ? [lindex $dv0 0] : [lindex $dv0 1]}]")
  lines.push("set d0 [expr {$ax0 > [lindex $dv0 2] ? $ax0 : [lindex $dv0 2]}]")
  lines.push("set k0 [expr {100.0 / $d0}]")
  lines.push("$s0 move [list [list $k0 0 0 0] [list 0 $k0 0 0] [list 0 0 $k0 0] [list 0 0 0 1]]")
  lines.push("$s0 delete")
  lines.push("display resetview")
  lines.push(`for {set i ${startIdx}} {$i < ${endIdx}} {incr i} {`)
  lines.push("  animate goto $i")
  // Center each frame on the origin: the merged DCD keeps raw (unwrapped)
  // coordinates whose earlier frames drift far from the box, which VMD's
  // ribbon/normal calculation turns into an invisible flat-white cartoon.
  lines.push("  set sel [atomselect top all]")
  lines.push("  set mm [robustbb $sel]")
  lines.push("  set lo [lindex $mm 0]")
  lines.push("  set hi [lindex $mm 1]")
  lines.push("  $sel moveby [vecscale -1 [vecadd $lo [vecscale 0.5 [vecsub $hi $lo]]]]")
  // Normalize the frame's extent so the molecule fills ~0.618 of the frame.
  lines.push("  set dv [vecsub $hi $lo]")
  lines.push("  set ax [expr {[lindex $dv 0] > [lindex $dv 1] ? [lindex $dv 0] : [lindex $dv 1]}]")
  lines.push("  set d [expr {$ax > [lindex $dv 2] ? $ax : [lindex $dv 2]}]")
  lines.push(`  set k [expr {${MOL_EXTENT} / $d}]`)
  lines.push("  $sel move [list [list $k 0 0 0] [list 0 $k 0 0] [list 0 0 $k 0] [list 0 0 0 1]]")
  lines.push("  $sel delete")
  lines.push(`  render TachyonInternal [format "${framePattern}" $i]`)
  lines.push("}")
  const tcl = lines.join("\n")
  const tclPath = join(workDir, `chunk_${startIdx}.tcl`)
  await writeFile(tclPath, tcl)

  await new Promise((resolve, reject) => {
    const child = spawn(VMD_BIN, ["-dispdev", "text", "-size", "800", "600", "-e", tclPath], { stdio: ["ignore", "pipe", "pipe"] })
    let stderr = ""
    child.stderr.on("data", d => { stderr += d })
    let lastCount = -1
    let lastChange = Date.now()
    const watchdog = setInterval(async () => {
      job.progress = await framesProgress(workDir, expected)
      const count = (await readdir(workDir)).filter(f => f.endsWith(".tga")).length
      if (count !== lastCount) {
        lastCount = count
        lastChange = Date.now()
      } else if (Date.now() - lastChange > WATCHDOG_MS) {
        clearInterval(watchdog)
        child.kill("SIGKILL")
        reject(new Error(`VMD stalled while rendering frames ${startIdx}-${endIdx - 1} (no new frame for ${Math.round(WATCHDOG_MS / 1000)}s)`))
      }
    }, 5000)
    child.on("error", err => { clearInterval(watchdog); reject(err) })
    child.on("exit", code => {
      clearInterval(watchdog)
      if (code !== 0) reject(new Error(`VMD rendering failed (exit ${code}): ${stderr.slice(-500)}`))
      else resolve()
    })
  })
}

async function renderVideo(taskId, replica, job, { fps = FPS, width = WIDTH, height = HEIGHT, maxFrames = MAX_FRAMES, full = false, format = "mp4", annotations = [], signature = "" } = {}) {
  const cacheDir = await getTrajectoryCacheDir(taskId)

  const pdbPath = join(cacheDir, "topology.pdb")
  if (!existsSync(pdbPath)) {
    const content = await getPDBData(taskId)
    if (!content) throw new Error("PDB structure not found")
    await writeFile(pdbPath, content)
  }

  // full: use the complete merged DCD (all cycles). tail (default): render the
  // same tail window the viewer displays, falling back to the full DCD when the
  // tail has not been generated yet.
  let dcdPath
  if (full) {
    dcdPath = join(cacheDir, `replica_${replica}.dcd`)
    if (!existsSync(dcdPath)) await syncTrajectoryFiles(taskId)
  } else {
    dcdPath = join(cacheDir, "last100", `replica_${replica}.dcd`)
    if (!existsSync(dcdPath)) await syncTrajectoryFiles(taskId)
    if (!existsSync(dcdPath)) {
      const fullDcd = join(cacheDir, `replica_${replica}.dcd`)
      dcdPath = existsSync(fullDcd) ? fullDcd : null
    }
  }
  if (!dcdPath || !existsSync(dcdPath)) throw new Error("No DCD trajectory available to render")

  const nf = await readDCDNframes(dcdPath)
  const step = Math.max(1, Math.ceil(nf / maxFrames))
  const expected = Math.ceil(nf / step)

  // Format-specific workdir: GIF and MP4 renders of the same replica may run
  // concurrently, and a shared workdir lets the first job's cleanup delete the
  // other's in-flight TGA frames.
  const workDir = join(cacheDir, "video", "work", `replica_${replica}${full ? "_full" : ""}_${format}`)
  await rm(workDir, { recursive: true, force: true })
  await mkdir(workDir, { recursive: true })

  job.status = "rendering"
  job.progress = 0
  for (let start = 0; start < expected; start += CHUNK_SIZE) {
    const end = Math.min(expected, start + CHUNK_SIZE)
    await renderChunk(job, dcdPath, pdbPath, workDir, step, start, end, expected, annotations)
  }

  const rendered = (await readdir(workDir)).filter(f => f.endsWith(".tga")).length
  if (rendered === 0) throw new Error("VMD produced no frames")

  job.status = "encoding"
  job.progress = 99

  const outDir = join(cacheDir, "video")
  await mkdir(outDir, { recursive: true })
  const ext = format === "gif" ? "gif" : "mp4"
  const finalPath = join(outDir, fileName(replica, full, format))
  const tmpPath = join(outDir, `replica_${replica}${full ? "_full" : ""}.part.${ext}`)

  const ffmpeg = await getFFmpegBin()
  if (format === "gif") {
    // Animated GIF. The trihedron is disabled at render time (`axes location
    // Off`), so no drawbox is needed. The molecule is centered in the 608-tall
    // source frame, so scaling the full frame to 640x480 keeps it centered.
    const vf =
      `fps=12,scale=640:480:flags=lanczos,` +
      "split[s0][s1];[s0]palettegen=stats_mode=full[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3"
    await execFileP(ffmpeg, [
      "-y", "-framerate", String(fps),
      "-i", join(workDir, "frame_%05d.tga"),
      "-vf", vf,
      "-loop", "0",
      tmpPath,
    ])
  } else {
    const vf = `scale=${width}:${height}:force_original_aspect_ratio=decrease,pad=${width}:${height}:(ow-iw)/2:(oh-ih)/2:color=black`
    await execFileP(ffmpeg, [
      "-y", "-framerate", String(fps),
      "-i", join(workDir, "frame_%05d.tga"),
      "-vf", vf,
      "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
      tmpPath,
    ])
  }
  await rename(tmpPath, finalPath)
  await writeFile(`${finalPath}.sig`, signature)
  await rm(workDir, { recursive: true, force: true })

  job.status = "done"
  job.progress = 100
  console.log(`[TrajectoryVideo] ${taskId} rep${replica}: ${expected} frames encoded as ${ext} -> ${finalPath}`)
}
