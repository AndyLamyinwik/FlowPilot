import type { JsonValue } from './workflow'

export type TriggerType = 'manual' | 'schedule'
export type ExecutionStatus = 'running' | 'success' | 'failed' | 'interrupted' | 'skipped' | (string & {})
export type NodeExecutionStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped' | (string & {})

export interface ExecutionError {
  code: string
  message: string
  node_id: string | null
}

export interface NodeExecutionResult {
  node_id: string
  status: NodeExecutionStatus
  output: JsonValue
  error: ExecutionError | null
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
}

export interface ExecutionResult {
  execution_id: string
  workflow_id: string
  status: ExecutionStatus
  started_at: string
  finished_at: string | null
  node_results: NodeExecutionResult[]
  error: ExecutionError | null
  // The synchronous execute response omits these history-only fields.
  trigger_type?: TriggerType
  duration_ms?: number | null
}

export interface ExecutionSummary {
  execution_id: string
  workflow_id: string
  trigger_type: TriggerType
  status: ExecutionStatus
  started_at: string
  finished_at: string | null
  duration_ms: number | null
}

export interface ExecutionDetail extends ExecutionSummary {
  node_results: NodeExecutionResult[]
  error: ExecutionError | null
  created_at: string
  definition_hash: string
  outputs_stored: boolean
  history_truncated: boolean
}

export interface ExecutionHistoryPage {
  items: ExecutionSummary[]
  total: number
  limit: number
  offset: number
}

export interface HistoryQuery {
  limit?: number
  offset?: number
  status?: string
}
