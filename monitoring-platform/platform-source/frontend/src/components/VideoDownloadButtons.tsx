import { useEffect, useRef, useState } from "react"
import { COLOR } from "../colors"

interface VideoDownloadButtonsProps {
  taskId: string
  replica: number
  /** true = full trajectory render, false = tail (last N cycles) window. */
  full?: boolean
}

interface VideoState {
  status: string
  progress?: number
  error?: string
}

const FORMATS = ["mp4", "gif"] as const
type Format = typeof FORMATS[number]

/** "Download MP4" / "Download GIF" buttons for the trajectory animation.
 *  Every click re-renders on the server (the backend deletes any cached file
 *  up front) and polls /status until the fresh file is ready, then downloads
 *  it. MP4 and GIF run fully independently (their own state + poll), so they
 *  can render in parallel; state is keyed by (replica, full, format), so
 *  switching the active replica never clobbers an in-flight render and its
 *  progress is still there when you switch back. */
export function VideoDownloadButtons({ taskId, replica, full = false }: VideoDownloadButtonsProps) {
  const [states, setStates] = useState<Record<string, VideoState>>({})
  const pollsRef = useRef<Map<string, number>>(new Map())

  const keyOf = (format: Format) => `${replica}:${full ? "1" : "0"}:${format}`
  const statusUrl = (format: Format) =>
    `/api/video/status?taskId=${encodeURIComponent(taskId)}&replica=${replica}&format=${format}${full ? "&full=1" : ""}`
  const renderUrl = (format: Format) =>
    `/api/video/render?taskId=${encodeURIComponent(taskId)}&replica=${replica}&format=${format}${full ? "&full=1" : ""}`

  useEffect(() => () => {
    for (const id of pollsRef.current.values()) clearInterval(id)
    pollsRef.current.clear()
  }, [])

  const triggerVideoDownload = (url: string) => {
    const a = document.createElement("a")
    a.href = url
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  const stopPoll = (k: string) => {
    const id = pollsRef.current.get(k)
    if (id != null) {
      clearInterval(id)
      pollsRef.current.delete(k)
    }
  }

  const startPoll = (format: Format) => {
    const k = keyOf(format)
    if (pollsRef.current.has(k)) return
    const id = window.setInterval(async () => {
      try {
        const res = await fetch(statusUrl(format))
        const d = await res.json()
        if (d.status === "done") {
          stopPoll(k)
          setStates(prev => ({ ...prev, [k]: { status: "done" } }))
          triggerVideoDownload(d.url)
          window.setTimeout(() => setStates(prev => ({ ...prev, [k]: { status: "idle" } })), 4000)
        } else if (d.status === "error") {
          stopPoll(k)
          setStates(prev => ({ ...prev, [k]: { status: "error", error: d.error } }))
        } else {
          setStates(prev => ({ ...prev, [k]: { status: d.status, progress: d.progress } }))
        }
      } catch {
        // transient error: keep polling
      }
    }, 3000)
    pollsRef.current.set(k, id)
  }

  const handleDownloadVideo = async (format: Format) => {
    try {
      const res = await fetch(renderUrl(format), { method: "POST" })
      const d = await res.json()
      if (d.url) return triggerVideoDownload(d.url)
      setStates(prev => ({ ...prev, [keyOf(format)]: { status: d.status || "rendering", progress: d.progress } }))
      startPoll(format)
    } catch (e: any) {
      setStates(prev => ({ ...prev, [keyOf(format)]: { status: "error", error: e.message } }))
    }
  }

  // Resume progress polling when returning to a replica that has an in-flight
  // render (its poll keeps running server-side while we are away).
  useEffect(() => {
    for (const format of FORMATS) {
      const st = states[keyOf(format)]
      if ((st?.status === "rendering" || st?.status === "encoding") && !pollsRef.current.has(keyOf(format))) {
        startPoll(format)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replica])

  const mp4 = states[keyOf("mp4")]
  const gif = states[keyOf("gif")]
  const mp4Busy = mp4?.status === "rendering" || mp4?.status === "encoding"
  const gifBusy = gif?.status === "rendering" || gif?.status === "encoding"

  const label = (s: VideoState | undefined, kind: string) =>
    s?.status === "rendering" || s?.status === "encoding"
      ? `Rendering ${s.progress ?? 0}%`
      : s?.status === "error"
        ? `Retry ${kind}`
        : `Download ${kind}`

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <button
        onClick={() => handleDownloadVideo("mp4")}
        disabled={mp4Busy}
        title="Render the trajectory animation as an MP4 on the server and download it"
        style={{
          padding: "6px 14px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600,
          cursor: mp4Busy ? "progress" : "pointer",
          background: COLOR.accent, color: "white",
          opacity: mp4Busy ? 0.75 : 1,
          transition: "all 0.15s",
        }}
      >
        {label(mp4, "MP4")}
      </button>
      <button
        onClick={() => handleDownloadVideo("gif")}
        disabled={gifBusy}
        title="Render the trajectory animation as an animated GIF on the server and download it"
        style={{
          padding: "6px 14px", borderRadius: 8, border: "none", fontSize: 13, fontWeight: 600,
          cursor: gifBusy ? "progress" : "pointer",
          background: "transparent", color: COLOR.accent,
          outline: `1px solid ${COLOR.accent}`,
          opacity: gifBusy ? 0.75 : 1,
          transition: "all 0.15s",
        }}
      >
        {label(gif, "GIF")}
      </button>
    </div>
  )
}
