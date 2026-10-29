import type { ExecutionError } from '../types/execution'
import type { JsonValue, ValidationIssue } from '../types/workflow'

const sensitiveKeys = new Set([
  'password', 'passwd', 'pwd', 'apikey', 'xapikey', 'secret', 'clientsecret',
  'accesstoken', 'refreshtoken', 'authtoken', 'xauthtoken', 'bearertoken',
  'authorization', 'proxyauthorization', 'cookie', 'setcookie', 'privatekey',
  'token', 'credentials',
])

const errorSummaries: Record<string, string> = {
  NODE_EXECUTION_FAILED: 'Node execution failed.', EXECUTION_FAILED: 'Workflow execution failed.',
  EXECUTION_INTERRUPTED: 'Execution was interrupted; it has not been automatically retried.',
  HTTP_TIMEOUT: 'HTTP request timed out.', HTTP_CONNECTION_ERROR: 'HTTP connection failed.',
  HTTP_DNS_ERROR: 'HTTP target could not be resolved.', HTTP_REQUEST_FAILED: 'HTTP request failed.',
  HTTP_STATUS_ERROR: 'HTTP request returned an unsuccessful status.',
  HTTP_TARGET_BLOCKED: 'HTTP target is blocked by the public-address policy.',
  HTTP_HOST_NOT_ALLOWED: 'HTTP target is not in the host allowlist.',
  HTTP_HTTPS_REQUIRED: 'HTTP requests require HTTPS.', HTTP_INVALID_URL: 'HTTP URL is invalid.',
  HTTP_INVALID_HEADERS: 'HTTP headers are invalid.', HTTP_FORBIDDEN_HEADER: 'A sensitive or client-managed HTTP header is not allowed.',
  HTTP_INVALID_TIMEOUT: 'HTTP timeout must be greater than zero and at most 60 seconds.',
  HTTP_INVALID_BODY: 'HTTP body is invalid.', HTTP_UNSUPPORTED_METHOD: 'HTTP method is not supported.',
  HTTP_REQUEST_TOO_LARGE: 'HTTP request exceeds the size limit.', HTTP_RESPONSE_TOO_LARGE: 'HTTP response exceeds the size limit.',
  HTTP_INVALID_RESPONSE: 'HTTP response is invalid.', HTTP_REDIRECT_BLOCKED: 'HTTP redirects are not supported.',
  HTTP_RESPONSE_ENCODING_UNSUPPORTED: 'Compressed HTTP responses are not supported.',
  INVALID_NODE_CONFIG: 'Node configuration is invalid or incomplete.',
  INVALID_CONDITION_CONFIG: 'Condition configuration is invalid or incomplete.',
  INVALID_TRANSFORM_CONFIG: 'Transform configuration is invalid or incomplete.',
  INVALID_SCHEDULE_CONFIG: 'Schedule configuration is invalid or incomplete.',
  INVALID_SCHEDULE_CRON: 'Schedule requires a valid five-field Cron expression.',
  INVALID_SCHEDULE_TIMEZONE: 'Schedule requires a valid IANA timezone.',
  INVALID_SCHEDULE_CONTEXT: 'Schedule trigger context is invalid.',
  INVALID_DATA_SOURCE: 'Data source must be an upstream node in this workflow.',
  INVALID_DATA_PATH: 'Data path must use dot-separated keys or nonnegative indexes.',
  DATA_SOURCE_UNAVAILABLE: 'Referenced upstream output is unavailable in this execution.',
  DATA_FIELD_NOT_FOUND: 'Referenced data field was not found.',
  CONDITION_TYPE_MISMATCH: 'The data type is incompatible with this Condition operator.',
  INVALID_CONDITION_OUTPUT: 'Condition did not return a valid boolean result.',
  INVALID_NODE_OUTPUT: 'Node output is not supported JSON.', OUTPUT_LIMIT_EXCEEDED: 'Execution output exceeded the size limit.',
  WORKFLOW_ALREADY_RUNNING: 'Scheduled execution was skipped because the workflow was already running.',
  SCHEDULE_SKIPPED: 'Scheduled execution was skipped.', SCHEDULE_MISSED: 'Scheduled execution was missed.',
  SCHEDULE_MAX_INSTANCES: 'Scheduled execution was skipped because another instance was active.',
}

const validationSummaries: Record<string, string> = {
  DUPLICATE_NODE_ID: 'Duplicate node ID.', DUPLICATE_EDGE_ID: 'Duplicate edge ID.',
  INVALID_NODE_REFERENCE: 'An edge references a missing node.', UNREGISTERED_NODE_TYPE: 'A node type is no longer registered.',
  SELF_LOOP: 'A node connects to itself.', CYCLE_DETECTED: 'The workflow contains a cycle.',
  MISSING_TRIGGER: 'Workflow requires a trigger node.', MISSING_MANUAL_TRIGGER: 'Workflow requires exactly one Manual Trigger.',
  MULTIPLE_MANUAL_TRIGGERS: 'Only one Manual Trigger is allowed.', MISSING_SCHEDULE_TRIGGER: 'Workflow requires exactly one Schedule Trigger.',
  MULTIPLE_SCHEDULE_TRIGGERS: 'Only one Schedule Trigger is allowed.', TRIGGER_TYPE_MISMATCH: 'Trigger type does not match this operation.',
  MANUAL_TRIGGER_HAS_UPSTREAM: 'Manual Trigger cannot have upstream nodes.', SCHEDULE_TRIGGER_HAS_UPSTREAM: 'Schedule Trigger cannot have upstream nodes.',
  DISCONNECTED_NODE: 'A node is disconnected.', UNREACHABLE_NODE: 'A node cannot be reached from the trigger.',
  UNSUPPORTED_NODE_EXECUTOR: 'This node type has no implemented executor.', INVALID_WORKFLOW_DEFINITION: 'Workflow definition is invalid.',
  EXECUTION_NODE_LIMIT_EXCEEDED: 'Workflow exceeds the execution node limit.', INVALID_BRANCH_HANDLE: 'Condition edges require a true or false source handle.',
  UNSUPPORTED_EDGE_HANDLE: 'This connection uses an unsupported handle.', INVALID_SCHEDULE_TRIGGER: 'Workflow requires one Schedule Trigger.',
}

export function safeValidationIssueMessage(issue: Pick<ValidationIssue, 'code' | 'message'>): string {
  if (Object.hasOwn(validationSummaries, issue.code)) return validationSummaries[issue.code]
  if (Object.hasOwn(errorSummaries, issue.code)) return errorSummaries[issue.code]
  return 'Workflow validation reported an issue. Review the affected node configuration.'
}

/** Never display arbitrary exception or traceback text from an error response. */
export function safeExecutionError(error: ExecutionError | null | undefined): string {
  if (!error) return ''
  if (error.code === 'HTTP_STATUS_ERROR') {
    const status = /^HTTP request returned status ([1-5]\d{2})$/.exec(error.message)
    if (status) return `HTTP request returned status ${status[1]}.`
  }
  return Object.hasOwn(errorSummaries, error.code) ? errorSummaries[error.code] : 'Execution could not complete. No additional safe error summary is available.'
}

function redactText(value: string): string {
  return value
    .replace(/\b(authorization|proxy-authorization|cookie|set-cookie)\s*[:=]\s*[^\r\n]+/gi, '$1: [REDACTED]')
    .replace(/\bBearer\s+[a-z\d._~+\/-]+=*/gi, 'Bearer [REDACTED]')
    .replace(/(https?:\/\/)[^\s/@]+:[^\s/@]+@/gi, '$1[REDACTED]@')
    .replace(/([?&](?:api[_-]?key|token|password|secret)=)[^&#\s]*/gi, '$1[REDACTED]')
}

/** Additional UI redaction only; it cannot discover every secret in arbitrary text.
 * The traversal is bounded before JSON rendering, and never mutates API data.
 */
export function sanitizeOutput(value: unknown, maxChars = 32_768): JsonValue {
  let remaining = Math.max(128, Math.min(maxChars, 131_072))
  const seen = new Set<object>()
  function visit(item: unknown, depth: number): JsonValue {
    if (remaining <= 0 || depth > 32) return '[Display truncated]'
    remaining -= 4
    if (item === null || typeof item === 'boolean') return item
    if (typeof item === 'number') {
      if (!Number.isFinite(item)) return '[Unavailable number]'
      return Number.isInteger(item) && !Number.isSafeInteger(item) ? '[Integer outside browser safe range]' : item
    }
    if (typeof item === 'string') {
      const safe = redactText(item)
      const text = safe.slice(0, Math.min(remaining, 8192))
      remaining -= text.length
      return text.length < safe.length ? `${text}… [Display truncated]` : text
    }
    if (typeof item !== 'object') return '[Unavailable value]'
    if (seen.has(item)) return '[Circular value]'
    seen.add(item)
    if (Array.isArray(item)) {
      const output: JsonValue[] = []
      for (const child of item.slice(0, 200)) {
        if (remaining <= 0) break
        output.push(visit(child, depth + 1))
      }
      if (output.length < item.length) output.push('[Display truncated]')
      seen.delete(item)
      return output
    }
    const entries = Object.entries(item)
    const output: Record<string, JsonValue> = Object.create(null) as Record<string, JsonValue>
    let count = 0
    for (const [key, child] of entries.slice(0, 200)) {
      if (remaining <= 0) break
      const safeKey = redactText(key).slice(0, 256)
      remaining -= safeKey.length
      const normalized = key.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
      output[safeKey] = sensitiveKeys.has(normalized) ? '[REDACTED]' : visit(child, depth + 1)
      count += 1
    }
    if (count < entries.length) output['[Display truncated]'] = true
    seen.delete(item)
    return output
  }
  return visit(value, 0)
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isFinite(date.getTime()) ? `${date.toISOString().replace('T', ' ').replace('Z', '')} UTC` : 'Unavailable'
}

export const formatUTCTime = formatTimestamp

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '—'
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`
}
