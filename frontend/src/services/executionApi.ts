import type { ExecutionDetail, ExecutionError, ExecutionHistoryPage, ExecutionResult, ExecutionSummary, HistoryQuery, NodeExecutionResult } from '../types/execution'
import { requestJSON } from './workflowApi'

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const uuid = (value: unknown): value is string => typeof value === 'string' && /^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(value)
const text = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0
const timestamp = (value: unknown): value is string => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) && Number.isFinite(Date.parse(value))
const optionalTime = (value: unknown) => value === null || timestamp(value)
const duration = (value: unknown) => value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0)
const integer = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0

function json(value: unknown, depth = 0): boolean {
  if (depth > 128) return false
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return true
  if (typeof value === 'number') return Number.isFinite(value)
  if (Array.isArray(value)) return value.every(item => json(item, depth + 1))
  return object(value) && Object.values(value).every(item => json(item, depth + 1))
}

function error(value: unknown): value is ExecutionError | null {
  return value === null || (object(value) && text(value.code) && typeof value.message === 'string'
    && (value.node_id === null || typeof value.node_id === 'string'))
}

function node(value: unknown): value is NodeExecutionResult {
  return object(value) && text(value.node_id) && text(value.status)
    && json(value.output) && error(value.error) && optionalTime(value.started_at)
    && optionalTime(value.finished_at) && duration(value.duration_ms)
}

function nodes(value: unknown): value is NodeExecutionResult[] {
  if (!Array.isArray(value) || !value.every(node)) return false
  return new Set(value.map(item => item.node_id)).size === value.length
}

function base(value: unknown): value is Record<string, unknown> {
  return object(value) && uuid(value.execution_id) && uuid(value.workflow_id)
    && text(value.status) && timestamp(value.started_at) && optionalTime(value.finished_at)
}

function assertExecution(value: unknown): asserts value is ExecutionResult {
  if (!base(value) || !nodes(value.node_results) || !error(value.error)) throw new Error('Invalid execution result.')
}

function summary(value: unknown): value is ExecutionSummary {
  return base(value) && (value.trigger_type === 'manual' || value.trigger_type === 'schedule') && duration(value.duration_ms)
}

function assertDetail(value: unknown): asserts value is ExecutionDetail {
  if (!summary(value) || !object(value) || !nodes(value.node_results) || !error(value.error)
    || !timestamp(value.created_at) || typeof value.definition_hash !== 'string'
    || typeof value.outputs_stored !== 'boolean' || typeof value.history_truncated !== 'boolean') throw new Error('Invalid execution detail.')
}

export function executeWorkflow(workflowId: string, signal?: AbortSignal): Promise<ExecutionResult> {
  return requestJSON(`/workflows/${encodeURIComponent(workflowId)}/execute`, { method: 'POST' },
    (value): asserts value is ExecutionResult => {
      assertExecution(value)
      if (value.workflow_id !== workflowId) throw new Error('Execution workflow mismatch.')
    }, signal, { resource: 'execution', operation: 'execute', timeoutMs: null })
}

export function getExecutionHistory(workflowId: string, query: HistoryQuery = {}, signal?: AbortSignal): Promise<ExecutionHistoryPage> {
  const limit = query.limit ?? 20
  const offset = query.offset ?? 0
  const parameters = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (query.status && query.status !== 'all') parameters.set('status', query.status)
  return requestJSON(`/workflows/${encodeURIComponent(workflowId)}/executions?${parameters}`, {},
    (value): asserts value is ExecutionHistoryPage => {
      if (!object(value) || !Array.isArray(value.items) || !value.items.every(summary)
        || !integer(value.total) || !integer(value.limit) || !integer(value.offset)
        || value.limit !== limit || value.offset !== offset || value.items.length > limit
        || value.items.some(item => item.workflow_id !== workflowId)
        || new Set(value.items.map(item => item.execution_id)).size !== value.items.length) throw new Error('Invalid execution history.')
    }, signal, { resource: 'history' })
}

export function getExecution(executionId: string, signal?: AbortSignal): Promise<ExecutionDetail> {
  return requestJSON(`/executions/${encodeURIComponent(executionId)}`, {},
    (value): asserts value is ExecutionDetail => {
      assertDetail(value)
      if (value.execution_id !== executionId) throw new Error('Execution ID mismatch.')
    }, signal, { resource: 'execution' })
}
