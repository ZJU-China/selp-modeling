export type MetricKey = "e2e" | "rg"

export const METRIC_META: Record<MetricKey, { label: string; short: string; unit: string }> = {
  e2e: { label: "End-to-end distance", short: "E2E", unit: "nm" },
  rg: { label: "Radius of gyration", short: "Rg", unit: "nm" },
}

export interface ConvergenceBlock {
  idx: number
  mean: number
  std: number
  n: number
}

export interface MetricDetails {
  mean_diff: number | null
  std_ratio: number | null
  mean_prev: number | null
  mean_curr: number | null
  std_prev: number | null
  std_curr: number | null
}

export interface MetricReplicaResult {
  converged: boolean
  n_blocks: number
  last: number | null
  blocks: ConvergenceBlock[]
  recent_cycles: { cycle: number; value: number }[]
  details: MetricDetails
}

export interface MetricThreshold {
  mean_diff: number
  std_ratio: number
  block_size: number
  unit: string
}

export interface MetricOverall {
  all_converged: boolean
  converged_replicas: number
}

export interface ReplicaConvergence {
  n_frames: number
  last_e2e: number | null
  last_rg: number | null
  converged: boolean
  metrics: Record<MetricKey, MetricReplicaResult>
  error?: string
}

export interface ConvergenceThresholds {
  metrics: Record<MetricKey, MetricThreshold>
  mean_diff_nm?: number
  std_ratio?: number
  block_size_cycles?: number
}

export interface CycleInfo {
  block_size: number
  recent_window: number
  total: number
  in_block: number
}

export interface ConvergenceData {
  converged: boolean
  stable_checks: number
  required_checks: number
  all_replicas_converged: boolean
  all_metrics_converged: boolean
  stopped: boolean
  cycles: CycleInfo
  metrics: Record<MetricKey, MetricOverall>
  thresholds: ConvergenceThresholds
  replicas: Record<string, ReplicaConvergence>
  error?: string
}
