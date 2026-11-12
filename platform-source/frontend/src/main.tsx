import { createRoot } from "react-dom/client"
import { App } from "./flow/App"
import { ThemeProvider } from "./theme"
import { FlowHeader } from "./flow/FlowHeader"
import "./styles/index.css"

createRoot(document.getElementById("root")!).render(
  <ThemeProvider>
    <FlowHeader />
    <App />
  </ThemeProvider>
)
