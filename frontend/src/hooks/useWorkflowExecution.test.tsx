import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ExecutionResult } from '../types/execution'
import type { FlowNode, WorkflowValidationReport } from '../types/workflow'
import { ApiError } from '../services/workflowApi'
import useWorkflowExecution from './useWorkflowExecution'

const calls = vi.hoisted(() => ({ execute: vi.fn(), validate: vi.fn() }))
vi.mock('../services/executionApi', () => ({ executeWorkflow: calls.execute }))
vi.mock('../services/workflowApi', async (load) => ({ ...await load<typeof import('../services/workflowApi')>(), validateWorkflow: calls.validate }))

const id = '36b233c6-2246-4663-8c65-c6da37372b9f'
const secondId = 'ca4ee7a8-bada-4d5f-83cc-be99a1b6fc9e'
const executionId = '8a235029-4b96-45dd-ae53-20b3a8561743'
const node: FlowNode = { id: 'manual', type: 'flowpilotNode', position: { x: 0, y: 0 }, data: { nodeType: 'trigger.manual', name: 'Original node name', config: {} } }
const valid: WorkflowValidationReport = { can_save: true, structural: { valid: true, errors: [], warnings: [] }, execution_readiness: { valid: true, errors: [], warnings: [] } }
const execution: ExecutionResult = { execution_id: executionId, workflow_id: id, status: 'success', started_at: '2026-10-29T00:00:00Z', finished_at: '2026-10-29T00:00:01Z', error: null, node_results: [{ node_id: 'manual', status: 'success', output: { trigger: 'manual' }, started_at: '2026-10-29T00:00:00Z', finished_at: '2026-10-29T00:00:01Z', duration_ms: 1000, error: null }] }

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((fulfill, fail) => { resolve = fulfill; reject = fail })
  return { promise, resolve, reject }
}

function options() {
  return { workflowId: id as string | null, workflowName: 'Original workflow', nodes: [node], dirty: false, revision: 0, epoch: 0, onComplete: vi.fn(), onNotice: vi.fn() }
}

beforeEach(() => {
  vi.resetAllMocks()
  calls.validate.mockResolvedValue(structuredClone(valid))
  calls.execute.mockResolvedValue(structuredClone(execution))
})

describe('execution admission and request identity', () => {
  it('does notsubmitExecute wheneditingcontinuesduringthepreflightrequest', async () => {
    const check = deferred<WorkflowValidationReport>()
    calls.validate.mockReturnValue(check.promise)
    const initial = options()
    const hook = renderHook((props) => useWorkflowExecution(props), { initialProps: initial })
    let pending!: Promise<void>
    act(() => { pending = hook.result.current.run() })
    expect(hook.result.current.validating).toBe(true)
    expect(hook.result.current.running).toBe(false)
    hook.rerender({ ...initial, dirty: true, revision: 1 })
    await act(async () => { check.resolve(valid); await pending })
    expect(calls.execute).not.toHaveBeenCalled()
    expect(initial.onNotice).toHaveBeenCalledWith(expect.objectContaining({ text: expect.stringContaining('changed during validation') }))
    expect(hook.result.current.running).toBe(false)
  })

  it('uses a synchronous guard againstdoubleclicksandreleasesitaftercompletion', async () => {
    const run = deferred<ExecutionResult>()
    calls.execute.mockReturnValueOnce(run.promise)
    const initial = options()
    const hook = renderHook((props) => useWorkflowExecution(props), { initialProps: initial })
    let first!: Promise<void>
    await act(async () => { first = hook.result.current.run(); void hook.result.current.run(); await Promise.resolve() })
    expect(calls.validate).toHaveBeenCalledOnce()
    expect(calls.execute).toHaveBeenCalledOnce()
    expect(hook.result.current.running).toBe(true)
    await act(async () => { run.resolve(execution); await first })
    expect(hook.result.current.running).toBe(false)
    await act(async () => { await hook.result.current.run() })
    expect(calls.execute).toHaveBeenCalledTimes(2)
  })

  it('doesnotlet anoldreloadresponse unlock oroverwritea newerexecution', async () => {
    const firstRun = deferred<ExecutionResult>()
    const secondRun = deferred<ExecutionResult>()
    calls.execute.mockReturnValueOnce(firstRun.promise).mockReturnValueOnce(secondRun.promise)
    const initial = options()
    const hook = renderHook((props) => useWorkflowExecution(props), { initialProps: initial })
    let first!: Promise<void>
    await act(async () => { first = hook.result.current.run(); await Promise.resolve() })
    const oldSignal = calls.execute.mock.calls[0][1] as AbortSignal
    hook.rerender({ ...initial, epoch: 1 })
    expect(oldSignal.aborted).toBe(true)
    let second!: Promise<void>
    await act(async () => { second = hook.result.current.run(); await Promise.resolve() })
    await act(async () => { firstRun.resolve(execution); await first })
    expect(hook.result.current.execution).toBeNull()
    await act(async () => { await hook.result.current.run() })
    expect(calls.execute).toHaveBeenCalledTimes(2)
    const fresh = { ...execution, execution_id: secondId }
    await act(async () => { secondRun.resolve(fresh); await second })
    expect(hook.result.current.execution?.execution_id).toBe(secondId)
  })

  it('clearsresultswhenswitchingworkflowandignoresthelateoldresult', async () => {
    const run = deferred<ExecutionResult>()
    calls.execute.mockReturnValue(run.promise)
    const initial = options()
    const hook = renderHook((props) => useWorkflowExecution(props), { initialProps: initial })
    let pending!: Promise<void>
    await act(async () => { pending = hook.result.current.run(); await Promise.resolve() })
    hook.rerender({ ...initial, workflowId: secondId, epoch: 1 })
    await act(async () => { run.resolve(execution); await pending })
    expect(hook.result.current.execution).toBeNull()
    expect(initial.onComplete).not.toHaveBeenCalled()
    expect(hook.result.current.running).toBe(false)
  })

  it('keeps namesfromtheexecutedsnapshotandmarksaneditedcanvasstale', async () => {
    const run = deferred<ExecutionResult>()
    calls.execute.mockReturnValue(run.promise)
    const initial = options()
    const hook = renderHook((props) => useWorkflowExecution(props), { initialProps: initial })
    let pending!: Promise<void>
    await act(async () => { pending = hook.result.current.run(); await Promise.resolve() })
    hook.rerender({ ...initial, revision: 1, dirty: true, workflowName: 'Changed workflow', nodes: [{ ...node, data: { ...node.data, name: 'Changed node' } }] })
    await act(async () => { run.resolve(execution); await pending })
    expect(hook.result.current.executionName).toBe('Original workflow')
    expect(hook.result.current.executionNodeNames.manual).toBe('Original node name')
    expect(hook.result.current.stale).toBe(true)
    expect(initial.onComplete).toHaveBeenCalledOnce()
  })

  it('treatsHTTP200 failed asafinishedexecutionandrefresheshistory', async () => {
    calls.execute.mockResolvedValue({ ...execution, status: 'failed', error: { code: 'NODE_EXECUTION_FAILED', message: 'Node execution failed', node_id: 'manual' } })
    const initial = options()
    const hook = renderHook((props) => useWorkflowExecution(props), { initialProps: initial })
    await act(async () => { await hook.result.current.run() })
    expect(hook.result.current.execution?.status).toBe('failed')
    expect(initial.onComplete).toHaveBeenCalledOnce()
    expect(initial.onNotice).not.toHaveBeenCalled()
  })

  it('doesnotmanufactureafailedexecutiononstoragefailureandreleasesguard', async () => {
    calls.execute.mockRejectedValueOnce(new ApiError(503, 'Execution storage is unavailable. The outcome is unknown.'))
    const initial = options()
    const hook = renderHook((props) => useWorkflowExecution(props), { initialProps: initial })
    await act(async () => { await hook.result.current.run() })
    expect(hook.result.current.execution).toBeNull()
    expect(initial.onNotice).toHaveBeenCalledWith(expect.objectContaining({ text: expect.stringContaining('outcome is unknown') }))
    expect(hook.result.current.running).toBe(false)
    await act(async () => { await hook.result.current.run() })
    expect(calls.execute).toHaveBeenCalledTimes(2)
  })

  it('doesnotcallapreflightconnectionfailureanunknownexecutionoutcome', async () => {
    calls.validate.mockRejectedValue(new ApiError(null, 'Cannot reach the backend.'))
    const initial = options()
    const hook = renderHook((props) => useWorkflowExecution(props), { initialProps: initial })
    await act(async () => { await hook.result.current.run() })
    expect(calls.execute).not.toHaveBeenCalled()
    expect(initial.onNotice).toHaveBeenCalledWith({ kind: 'error', text: 'Cannot reach the backend.' })
    expect(hook.result.current.running).toBe(false)
    expect(hook.result.current.validating).toBe(false)
  })

  it('abortsontheactualrequestwhenunmountedwithoutcompletionupdates', async () => {
    const run = deferred<ExecutionResult>()
    calls.execute.mockReturnValue(run.promise)
    const initial = options()
    const hook = renderHook((props) => useWorkflowExecution(props), { initialProps: initial })
    let pending!: Promise<void>
    await act(async () => { pending = hook.result.current.run(); await Promise.resolve() })
    const signal = calls.execute.mock.calls[0][1] as AbortSignal
    hook.unmount()
    expect(signal.aborted).toBe(true)
    await act(async () => { run.resolve(execution); await pending })
    await waitFor(() => expect(initial.onComplete).not.toHaveBeenCalled())
  })
})
