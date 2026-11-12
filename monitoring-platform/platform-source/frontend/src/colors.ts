// Component-level color constants (original scheme). Values mirror
// styles/colors.css — the CSS side is the canonical source; keep them in sync.

// Original fixed replica palette (blue / orange / green / purple). Keep the
// function API so callers work for any replica count: beyond the 4 base
// colors the palette cycles, and the fallback is the neutral gray.
const REPLICA_BASE = ["#007aff", "#ff9500", "#34c759", "#af52de"]

/** `n` replica colors drawn from the original scheme — the same 4 base
 *  colors in order, cycled when a task has more than 4 replicas. Index
 *  results by the replica's 0-based id, e.g. REPLICAS_COLORS(n)[replicaId]. */
export function REPLICAS_COLORS(n: number): string[] {
  if (n <= 0) return []
  return Array.from({ length: n }, (_, i) => REPLICA_BASE[i % REPLICA_BASE.length])
}

export const TEMP_COLORS: Record<string, string> = {
  "280K": "#007aff",
  "315K": "#5ac8fa",
  "355K": "#ff9500",
  "400K": "#ff3b30",
}

export const COLOR = {
  accent: "#007aff",
  success: "#34c759",
  warning: "#ff9500",
  danger: "#ff3b30",
  info: "#5ac8fa",
  muted: "#86868b",
  mutedAlt: "#8e8e93",
  white: "#ffffff",
  cartoonLight: "#e8e8e8",
  nglBgDark: "#1a1a2e",
  running: "#3b82f6",
  ok: "#16a34a",
  error: "#dc2626",
  terminalBg: "#1c1c1e",
  terminalFg: "#f5f5f7",
  terminalError: "#ff6b6b",
  successSoft: "#dcfce7",
  successSoftBorder: "#bbf7d0",
  successSoftFg: "#166534",
  infoSoft: "#dbeafe",
  infoSoftBorder: "#bfdbfe",
  infoSoftFg: "#1e40af",
  dangerSoftFg: "#991b1b",
  fail: "#b91c1c",
  e2e: "#2563eb",
  rg: "#f59e0b",
} as const