import type {
  NodeTypeMetadata, ValidationIssue, ValidationResult, Workflow,
  WorkflowPayload, WorkflowSummary, WorkflowValidationReport,
} from '../types/workflow'
import { assertWorkflowDefinition } from '../utils/workflowAdapter'
import { getApiBaseUrl } from './api'
import { safeValidationIssueMessage } from '../utils/executionDisplay'

export class ApiError extends Error {
  readonly status: number | null
  readonly issues: ValidationIssue[]

  constructor(status: number | null, message: string, issues: ValidationIssue[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.issues = issues
  }
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function text(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function awareTime(value: unknown): value is string {
  return typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) && Number.isFinite(Date.parse(value))
}

function assertWorkflow(value: unknown, validateConfigValues = true): asserts value is Workflow {
  if (!object(value) || !text(value.id) || !/^[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}$/i.test(value.id) || !text(value.name)
    || (value.description !== null && typeof value.description !== 'string')
    || !awareTime(value.created_at) || !awareTime(value.updated_at)) {
    throw new Error('Invalid workflow response.')
  }
  assertWorkflowDefinition(value.definition, validateConfigValues)
}

function assertNodeTypes(value: unknown): asserts value is NodeTypeMetadata[] {
  if (!Array.isArray(value)) throw new Error('Invalid node registry response.')
  const types = new Set<string>()
  for (const item of value) {
    if (!object(item) || !text(item.type) || !text(item.display_name) || !text(item.category)
      || !text(item.description) || types.has(item.type)) throw new Error('Invalid node registry metadata.')
    types.add(item.type)
  }
}

function issue(value: unknown): value is ValidationIssue {
  return object(value) && text(value.code) && text(value.message)
    && (value.node_id == null || typeof value.node_id === 'string')
    && (value.edge_id == null || typeof value.edge_id === 'string')
}

function result(value: unknown): value is ValidationResult {
  return object(value) && typeof value.valid === 'boolean'
    && Array.isArray(value.errors) && value.errors.every(issue)
    && Array.isArray(value.warnings) && value.warnings.every(issue)
}

function assertValidationReport(value: unknown): asserts value is WorkflowValidationReport {
  if (!object(value) || typeof value.can_save !== 'boolean'
    || !result(value.structural) || !result(value.execution_readiness)) throw new Error('Invalid validation response.')
}

/** Use known API issue codes/locations, never raw traceback, config, input or ctx. */
function errorMessage(status: number, body: unknown): string {
  if (status === 404) return 'Workflow not found. It may have been deleted.'
  if (status === 409) return 'This workflow is running. Wait for it to finish before deleting it.'
  if (status === 422) {
    const labels: Record<string, string> = {
      DUPLICATE_NODE_ID: 'Duplicate node ID', DUPLICATE_EDGE_ID: 'Duplicate edge ID',
      INVALID_NODE_REFERENCE: 'An edge references a missing node',
      UNREGISTERED_NODE_TYPE: 'A node type is no longer registered', SELF_LOOP: 'A node connects to itself',
      CYCLE_DETECTED: 'The workflow contains a cycle',
    }
    if (object(body) && object(body.detail) && Array.isArray(body.detail.errors)) {
      const messages = body.detail.errors.flatMap(item => object(item) && typeof item.code === 'string'
        && Object.hasOwn(labels, item.code) ? [labels[item.code]] : [])
      if (messages.length) return `Workflow validation failed: ${[...new Set(messages)].slice(0, 3).join('; ')}.`
    }
    if (object(body) && Array.isArray(body.detail)) {
      const fields = body.detail.flatMap(item => {
        if (!object(item) || !Array.isArray(item.loc)) return []
        // Only known schema fields; dynamic config keys or rejected input never become UI text.
        return item.loc.filter((part): part is string => typeof part === 'string'
          && ['name', 'description', 'definition', 'schema_version', 'nodes', 'edges', 'position', 'config'].includes(part))
      })
      if (fields.length) return `Workflow validation failed. Check ${[...new Set(fields)].slice(0, 3).join(', ')}.`
    }
    return 'Workflow validation failed. Check node names, connections and configuration; credentials are not allowed.'
  }
  if (status === 503) return 'Backend storage is unavailable. Please try again later.'
  return `The backend could not complete the request (${status}). Please try again.`
}

export interface RequestOptions {
  resource?: 'workflow' | 'execution' | 'history' | 'schedule'
  operation?: 'execute'
  timeoutMs?: number | null
}

function safeIssues(body: unknown): ValidationIssue[] {
  if (!object(body) || !object(body.detail) || !Array.isArray(body.detail.errors)) return []
  return body.detail.errors.slice(0, 256).flatMap((item) => {
    if (!object(item) || typeof item.code !== 'string') return []
    const code = /^[A-Z][A-Z0-9_]{0,63}$/.test(item.code) ? item.code : 'INVALID_WORKFLOW'
    return [{ code, message: safeValidationIssueMessage({ code, message: '' }),
      node_id: typeof item.node_id === 'string' ? item.node_id.slice(0, 1024) : null,
      edge_id: typeof item.edge_id === 'string' ? item.edge_id.slice(0, 1024) : null }]
  })
}

function requestError(status: number, body: unknown, options: RequestOptions): ApiError {
  const issues = status === 422 ? safeIssues(body) : []
  if (!options.resource || options.resource === 'workflow') return new ApiError(status, errorMessage(status, body), issues)
  if (status === 404) return new ApiError(status, options.resource === 'execution' && options.operation !== 'execute'
    ? 'Execution not found. It may have expired or been deleted.' : 'Workflow not found. It may have been deleted.')
  if (status === 409) return new ApiError(status, 'Workflow is already running.')
  if (status === 422) return new ApiError(status, issues.length
    ? `Workflow validation failed: ${issues.slice(0, 3).map((item) => item.message).join(' ')}`
    : 'Workflow validation failed. Review the saved trigger and node configuration.', issues)
  if (status === 503) return new ApiError(status, options.operation === 'execute'
    ? 'Execution storage is unavailable. The execution outcome may be unknown; check history before running again.'
    : 'Backend storage is unavailable. Please try again later.')
  return new ApiError(status, options.operation === 'execute'
    ? 'The execution request could not be completed. Its outcome is unknown; check history before running again.'
    : `The backend could not complete the request (${status}). Please try again.`)
}

export async function requestJSON<T>(
  path: string, init: RequestInit, validate: (value: unknown) => asserts value is T,
  signal?: AbortSignal,
  options: RequestOptions = {},
): Promise<T> {
  const timeout = options.timeoutMs === null ? undefined : AbortSignal.timeout(options.timeoutMs ?? 10_000)
  const combinedSignal = signal && timeout ? AbortSignal.any([signal, timeout]) : signal ?? timeout
  let response: Response
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init.body ? { 'Content-Type': 'application/json' } : {}) },
      signal: combinedSignal,
    })
  } catch {
    if (options.operation === 'execute') throw new ApiError(null, signal?.aborted
      ? 'Execution request cancelled. The backend may still be running; check history before running again.'
      : 'Execution request lost its connection. The outcome is unknown; check history before running again.')
    if (signal?.aborted) throw new ApiError(null, 'Request cancelled.')
    if (timeout?.aborted) throw new ApiError(null, 'The request timed out. Please try again.')
    throw new ApiError(null, 'Cannot reach the backend. Check your connection and try again.')
  }
  let body: unknown
  try {
    body = response.status === 204 ? undefined : await response.json()
  } catch {
    if (timeout?.aborted) throw new ApiError(null, 'The request timed out. Please try again.')
    if (options.operation === 'execute') throw new ApiError(response.status, 'The execution response was unavailable. Its outcome is unknown; check history before running again.')
    throw response.ok ? new ApiError(response.status, 'The backend returned invalid data. Your current workflow has been kept.') : requestError(response.status, null, options)
  }
  if (!response.ok) throw requestError(response.status, body, options)
  try {
    validate(body)
  } catch (error) {
    if (options.operation === 'execute') throw new ApiError(response.status, 'The backend returned an invalid execution result. Its outcome is unknown; check history before running again.')
    if (options.resource && options.resource !== 'workflow') throw new ApiError(response.status, `The backend returned invalid ${options.resource} data.`)
    if (error instanceof Error && error.message.includes('browser safe range')) {
      throw new ApiError(response.status, 'This workflow contains numbers outside the browser safe integer range. It cannot be edited safely; the saved workflow and current canvas have not been changed.')
    }
    throw new ApiError(response.status, 'The backend returned invalid workflow data. Your current workflow has been kept.')
  }
  return body
}

const workflowPath = (id: string) => `/workflows/${encodeURIComponent(id)}`
const request = requestJSON

export async function listWorkflows(signal?: AbortSignal): Promise<WorkflowSummary[]> {
  const items = await request('/workflows', {}, (value): asserts value is Workflow[] => {
    if (!Array.isArray(value)) throw new Error('Expected a workflow list.')
    // Validate config object shape only: valid backend JSON can exceed browser
    // numeric limits. Discard all config values before exposing summary data;
    // direct editor loads keep the strict default validation.
    value.forEach(item => assertWorkflow(item, false))
  }, signal)
  return items.map(item => ({
    id: item.id, name: item.name, description: item.description,
    created_at: item.created_at, updated_at: item.updated_at,
    definition: {
      schema_version: item.definition.schema_version,
      nodes: item.definition.nodes.map(({ id, type, name }) => ({ id, type, name })),
      edges: item.definition.edges.map(edge => ({
        id: edge.id, source: edge.source, target: edge.target,
        ...(edge.source_handle === undefined ? {} : { source_handle: edge.source_handle }),
        ...(edge.target_handle === undefined ? {} : { target_handle: edge.target_handle }),
      })),
    },
  }))
}

export function getWorkflow(id: string, signal?: AbortSignal): Promise<Workflow> {
  return request(workflowPath(id), {}, assertWorkflow, signal)
}

export function createWorkflow(payload: WorkflowPayload, signal?: AbortSignal): Promise<Workflow> {
  return request('/workflows', { method: 'POST', body: JSON.stringify(payload) }, assertWorkflow, signal)
}

export function updateWorkflow(id: string, payload: WorkflowPayload, signal?: AbortSignal): Promise<Workflow> {
  return request(workflowPath(id), { method: 'PUT', body: JSON.stringify(payload) }, assertWorkflow, signal)
}

export function deleteWorkflow(id: string, signal?: AbortSignal): Promise<void> {
  return request(workflowPath(id), { method: 'DELETE' }, (value): asserts value is undefined => {
    if (value !== undefined) throw new Error('Expected an empty delete response.')
  }, signal)
}

export function getNodeTypes(signal?: AbortSignal): Promise<NodeTypeMetadata[]> {
  return request('/node-types', {}, assertNodeTypes, signal)
}

export function validateWorkflow(id: string, signal?: AbortSignal): Promise<WorkflowValidationReport> {
  return request(`${workflowPath(id)}/validate`, { method: 'POST' }, assertValidationReport, signal)
}
