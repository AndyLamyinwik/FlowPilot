import { describe, expect, it } from 'vitest'
import { formatDuration, formatTimestamp, safeExecutionError, safeValidationIssueMessage, sanitizeOutput } from './executionDisplay'

describe('execution display privacy andformatting', () => {
  it('redacts nestedcredentialfields withoutmodifying API data', () => {
    const source = { headers: { Authorization: 'secret-one', Cookie: 'secret-two', 'Proxy-Authorization': 'secret-three', Accept: 'application/json' }, nested: [{ api_key: 'secret-four', 'access-token': 'secret-five' }], result: false }
    const original = structuredClone(source)
    const safe = JSON.stringify(sanitizeOutput(source))
    expect(safe).not.toMatch(/secret-(one|two|three|four|five)/)
    expect(safe).toContain('[REDACTED]')
    expect(safe).toContain('application/json')
    expect(source).toEqual(original)
  })

  it('adds basic protection forcredentialtext andURL credentials', () => {
    const safe = JSON.stringify(sanitizeOutput(['Authorization: top-secret', 'Bearer token-secret', 'https://person:password@host.test/?api_key=query-secret']))
    expect(safe).not.toMatch(/top-secret|token-secret|password@|query-secret/)
  })

  it('keeps backendredaction anddoesnotinvent outputvalues', () => {
    expect(sanitizeOutput({ token: '[REDACTED]', output: null, value: 0, bool: false })).toEqual({ token: '[REDACTED]', output: null, value: 0, bool: false })
    expect(sanitizeOutput(Number.MAX_SAFE_INTEGER + 1)).toBe('[Integer outside browser safe range]')
  })

  it('bounds longorcyclicoutputs beforeviewerformatting', () => {
    const huge = { records: Array.from({ length: 1000 }, () => 'x'.repeat(10_000)) }
    const safe = JSON.stringify(sanitizeOutput(huge))
    expect(safe.length).toBeLessThan(34_000)
    expect(safe).toContain('Display truncated')
    const circular: Record<string, unknown> = {}
    circular.self = circular
    expect(sanitizeOutput(circular)).toEqual({ self: '[Circular value]' })
  })

  it('treats prototype-like keys as data withoutprototypewrites', () => {
    const source: unknown = JSON.parse('{"__proto__":{"polluted":true},"constructor":{"token":"secret-marker"}}')
    const safe = sanitizeOutput(source)
    expect(JSON.stringify(safe)).toContain('__proto__')
    expect(JSON.stringify(safe)).not.toContain('secret-marker')
    expect(Object.getPrototypeOf(safe)).toBeNull()
  })

  it('uses controlled errorsummaries andignores tracebacks orunknowncodes', () => {
    expect(safeExecutionError({ code: 'HTTP_TIMEOUT', message: 'Traceback secret-marker', node_id: 'http' })).toBe('HTTP request timed out.')
    expect(safeExecutionError({ code: 'HTTP_STATUS_ERROR', message: 'HTTP request returned status 503', node_id: 'http' })).toContain('503')
    expect(safeExecutionError({ code: 'constructor', message: 'secret-marker', node_id: null })).not.toContain('secret-marker')
    expect(safeValidationIssueMessage({ code: 'MISSING_MANUAL_TRIGGER', message: 'private-marker' })).toContain('Manual Trigger')
    expect(safeValidationIssueMessage({ code: 'FUTURE_CODE', message: 'private-marker' })).not.toContain('private-marker')
  })

  it('labels UTC timeexplicitly andformats absent/finite durations', () => {
    expect(formatTimestamp('2026-10-29T09:00:00+08:00')).toBe('2026-10-29 01:00:00.000 UTC')
    expect(formatTimestamp(null)).toBe('—')
    expect(formatTimestamp('invalid')).toBe('Unavailable')
    expect(formatDuration(1240)).toBe('1.24 s')
    expect(formatDuration(9)).toBe('9 ms')
    expect(formatDuration(null)).toBe('—')
  })
})
