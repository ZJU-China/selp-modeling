import { ThemeToggle } from "../theme"

// Minimal header. The original app's header carries the task <select>, which is
// meaningless here: this frontend is organised by flow, not by selected task.
export function FlowHeader() {
  return (
    <header className="header">
      <div className="header-inner">
        <a className="header-brand" href="#/">Flow Console</a>
        <nav className="header-nav">
          <a href="#/">Flows</a>
        </nav>
        <div className="header-right">
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
