import type { ReactNode } from "react"
import { useTheme, type ThemeMode } from "./ThemeContext"

const CYCLE: ThemeMode[] = ["light", "dark", "system"]

const ICONS: Record<ThemeMode, ReactNode> = {
  light: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  ),
  dark: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  ),
  system: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  ),
}

const LABELS: Record<ThemeMode, string> = {
  light: "Theme: light",
  dark: "Theme: dark",
  system: "Theme: system",
}

export function ThemeToggle() {
  const { mode, setMode } = useTheme()
  const next = CYCLE[(CYCLE.indexOf(mode) + 1) % CYCLE.length]

  return (
    <button
      className="theme-toggle"
      type="button"
      title={`${LABELS[mode]} (click for ${LABELS[next]})`}
      aria-label={LABELS[mode]}
      onClick={() => setMode(next)}
    >
      {ICONS[mode]}
    </button>
  )
}
