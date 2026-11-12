export interface TempConfig {
  num_replicas: number
  steps_per_cycle: number
  total_cycles: number
  temp_range: number[]
  target_temps: number[]
  method?: string
}

export interface TempReplica {
  id: number
  temp_avg: number
  temp_min: number
  temp_max: number
  exchange_count: number
  temp_trace: { step: number; temp: number }[]
}

export interface TempData {
  config: TempConfig
  replicas: Record<string, TempReplica>
  temp_visit_counts: Record<string, number>
}
