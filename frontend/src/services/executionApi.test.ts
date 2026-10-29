import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ExecutionDetail, ExecutionResult, ExecutionSummary } from '../types/execution'
import { executeWorkflow, getExecution, getExecutionHistory } from './executionApi'

const workflowId = 'a2696bb8-8122-43b1-a3d5-f2a29da89a67'
const executionId = 'b0c46982-e3ec-43f9-9379-61c85423f19c'
const otherId = '5005f581-613a-477a-b11b-72f11a07ef52'
const started = '2026-10-29T01:00:00Z'
const finished = '2026-10-29T01:00:02Z'
const result: ExecutionResult = {
  execution_id: executionId, workflow_id: workflowId, status: 'success', started_at: started,
  finished_at: finished, error: null, node_results: [{
    node_id: 'start', status: 'success', started_at: started, finished_at: finished,
    duration_ms: 2000, output: { trigger: 'manual' }, error: null,
  }],
}
const summary: ExecutionSummary = { execution_id: executionId, workflow_id: workflowId, status: 'success', trigger_type: 'manual', started_at: started, finished_at: finished, duration_ms: 2000 }
const detail: ExecutionDetail = { ...summary, node_results: result.node_results, error: null, created_at: started, definition_hash: 'abc', outputs_stored: false, history_truncated: false }
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status })

afterEach(() => { vi.useRealTimers() })

describe('execution API', () => {
  it('uses the configured base and preserves HTTP200 failed execution as a domain result', async () => {
    const failure = { ...result, status: 'failed', error: { code: 'HTTP_TIMEOUT', message: 'HTTP request timed out', node_id: 'http' } }
    const fetchMock = vi.fn().mockResolvedValue(response(failure))
    vi.stubGlobal('fetch', fetchMock)
    vi.stubEnv('VITE_API_BASE_URL', 'https://flowpilot.example/api/')
    await expect(executeWorkflow(workflowId)).resolves.toEqual(failure)
    expect(fetchMock).toHaveBeenCalledWith(`https://flowpilot.example/api/workflows/${workflowId}/execute`, expect.objectContaining({ method: 'POST', signal: undefined }))
  })

  it('keeps a synchronous execution pending past10seconds without manufacturing failure or retry', async () => {
    vi.useFakeTimers()
    const timeout = vi.spyOn(AbortSignal, 'timeout')
    let complete!: (value: Response) => void
    const fetchMock = vi.fn().mockImplementation(() => new Promise<Response>((resolve) => { complete = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    const caller = new AbortController()
    const pending = executeWorkflow(workflowId, caller.signal)
    await vi.advanceTimersByTimeAsync(15_000)
    expect(caller.signal.aborted).toBe(false)
    expect(timeout).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][1].signal).toBe(caller.signal)
    complete(response(result))
    await expect(pending).resolves.toEqual(result)
  })

  it('reports a clear409 without retrying', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ detail: 'private diagnostic' }, 409))
    vi.stubGlobal('fetch', fetchMock)
    await expect(executeWorkflow(workflowId)).rejects.toMatchObject({ status: 409, message: 'Workflow is already running.' })
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('retains safe readiness codes/nodeids while excluding arbitrary messages,input andctx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: { code: 'WORKFLOW_NOT_EXECUTABLE', errors: [
      { code: 'INVALID_NODE_CONFIG', message: 'Traceback credential-marker', node_id: 'http', input: 'credential-marker', ctx: { password: 'credential-marker' } },
      { code: 'constructor', message: 'credential-marker', node_id: 'logger' },
    ] } }, 422)))
    await expect(executeWorkflow(workflowId)).rejects.toMatchObject({ status: 422, issues: [
      { code: 'INVALID_NODE_CONFIG', message: 'Node configuration is invalid or incomplete.', node_id: 'http', edge_id: null },
      { code: 'INVALID_WORKFLOW', message: expect.any(String), node_id: 'logger', edge_id: null },
    ] })
    try { await executeWorkflow(workflowId) } catch (error) { expect(JSON.stringify(error)).not.toContain('credential-marker') }
  })

  it.each([503, 500])('keepsHTTP%s execution outcomes uncertain rather than retrying side effects', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'Traceback secret-marker' }, status)))
    await expect(executeWorkflow(workflowId)).rejects.toMatchObject({ status, message: expect.stringMatching(/outcome.*unknown/i) })
  })

  it('preserves unknown node status for UI fallback without renaming it success', async () => {
    const unusual = structuredClone(result)
    unusual.node_results[0].status = 'future_status'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(unusual)))
    await expect(executeWorkflow(workflowId)).resolves.toMatchObject({ node_results: [{ status: 'future_status' }] })
  })

  it.each([
    { ...result, workflow_id: otherId },
    { ...result, execution_id: 'not-an-id' },
    { ...result, started_at: '2026-10-29T01:00:00' },
    { ...result, node_results: [result.node_results[0], result.node_results[0]] },
    { ...result, node_results: [{ ...result.node_results[0], duration_ms: -1 }] },
  ])('rejects invalid or mismatched live results without claiming success', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(body)))
    await expect(executeWorkflow(workflowId)).rejects.toMatchObject({ message: expect.stringMatching(/invalid execution result.*outcome is unknown/i) })
  })

  it('treats malformedJSON and lost transport as uncertain execution outcomes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('not-json')).mockRejectedValueOnce(new TypeError('private network marker')))
    await expect(executeWorkflow(workflowId)).rejects.toThrow('outcome is unknown')
    await expect(executeWorkflow(workflowId)).rejects.toThrow('outcome is unknown')
  })

  it('does not imply caller cancellation stopped backend execution', async () => {
    const caller = new AbortController()
    caller.abort()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('private aborted', 'AbortError')))
    await expect(executeWorkflow(workflowId, caller.signal)).rejects.toThrow('backend may still be running')
  })

  it('uses server pagination andstatusfilter and accepts emptyhistory', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response({ items: [summary], total: 21, limit: 20, offset: 20 }))
      .mockResolvedValueOnce(response({ items: [], total: 0, limit: 20, offset: 0 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getExecutionHistory(workflowId, { offset: 20, status: 'success' })).resolves.toMatchObject({ total: 21, offset: 20 })
    expect(fetchMock.mock.calls[0][0]).toBe(`/api/workflows/${workflowId}/executions?limit=20&offset=20&status=success`)
    await expect(getExecutionHistory(workflowId)).resolves.toEqual({ items: [], total: 0, limit: 20, offset: 0 })
  })

  it('rejects crossworkflow history and wrongpagination', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(response({ items: [{ ...summary, workflow_id: otherId }], total: 1, limit: 20, offset: 0 }))
      .mockResolvedValueOnce(response({ items: [], total: 0, limit: 100, offset: 0 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getExecutionHistory(workflowId)).rejects.toThrow('invalid history data')
    await expect(getExecutionHistory(workflowId)).rejects.toThrow('invalid history data')
  })

  it('loads details without inventing unavailable outputs', async () => {
    const body = { ...detail, node_results: [{ ...result.node_results[0], output: null }] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(body)))
    await expect(getExecution(executionId)).resolves.toMatchObject({ outputs_stored: false, node_results: [{ output: null }] })
  })

  it('handles missing execution, wrongID andmalformedhistorymetadata', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response({ detail: 'secret-marker' }, 404))
      .mockResolvedValueOnce(response({ ...detail, execution_id: otherId }))
      .mockResolvedValueOnce(response({ ...detail, outputs_stored: 'false' })))
    await expect(getExecution(executionId)).rejects.toThrow('Execution not found')
    await expect(getExecution(executionId)).rejects.toThrow('invalid execution data')
    await expect(getExecution(executionId)).rejects.toThrow('invalid execution data')
  })
})
