import { TemperatureTrace as SharedTemperatureTrace } from "../shared/TemperatureTrace"
import type { TempData } from "./types"

export function TemperatureTrace({ data, animate }: { data: TempData; animate: boolean }) {
  return (
    <SharedTemperatureTrace
      replicas={data.replicas}
      config={data.config}
      animate={animate}
      title="Temperature Trace (All Replicas)"
      selectable
      yDomain={[240, 440]}
    />
  )
}
