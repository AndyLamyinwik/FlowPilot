import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ExecutionDetail, ExecutionHistoryPage, ExecutionSummary } from '../../types/execution'
import ExecutionHistory from './ExecutionHistory'

const mocks = vi.hoisted(() => ({ getExecutionHistory: vi.fn(), getExecution: vi.fn() }))
vi.mock('../../services/executionApi', () => mocks)
const WORKFLOW = 'workflow-1'
const TIME = '2026-10-29T09:00:00Z'
function summary(id: string, workflow = WORKFLOW, status = 'success'): ExecutionSummary {
  return { execution_id: id, workflow_id: workflow, status, trigger_type: 'manual', started_at: TIME, finished_at: TIME, duration_ms: 10 }
}
function page(items: ExecutionSummary[] = [], total = items.length, offset = 0): ExecutionHistoryPage {
  return { items, total, limit: 20, offset }
}
function detail(id: string, workflow = WORKFLOW): ExecutionDetail {
  return { ...summary(id, workflow), created_at: TIME, definition_hash: 'hash', outputs_stored: false, history_truncated: false,
    error: null, node_results: [{ node_id: 'historical-node', status: 'success', output: null, error: null,
      started_at: TIME, finished_at: TIME, duration_ms: 10 }] }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((a, b) => { resolve = a; reject = b })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.getExecutionHistory.mockResolvedValue(page())
  mocks.getExecution.mockResolvedValue(detail('run-1'))
})

describe('execution history', () => {
  it('requires a saved workflow without making a history request', () => {
    render(<ExecutionHistory workflowId={null} refreshKey={0} />)
    expect(screen.getByText('Save a workflow to view its execution history.')).toBeTruthy()
    expect(mocks.getExecutionHistory).not.toHaveBeenCalled()
  })

  it('loads a bounded first page and treats empty history as a normal state', async () => {
    render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    await screen.findByText('No executions yet.')
    expect(mocks.getExecutionHistory).toHaveBeenCalledWith(WORKFLOW, { limit: 20, offset: 0 }, expect.any(AbortSignal))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByText('0 of 0 executions')).toBeTruthy()
  })

  it('shows execution time, status, trigger and duration with detail actions', async () => {
    mocks.getExecutionHistory.mockResolvedValue(page([summary('run-1')]))
    render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Success')).toBeTruthy()
    expect(screen.getByText('Manual')).toBeTruthy()
    expect(screen.getByText('10 ms')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'View details run-1' })).toBeTruthy()
  })

  it.each(['success', 'failed', 'interrupted', 'skipped', 'running'])('requests the %s filter and resets pagination', async status => {
    render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    await screen.findByText('No executions yet.')
    fireEvent.change(screen.getByLabelText('History status'), { target: { value: status } })
    await waitFor(() => expect(mocks.getExecutionHistory).toHaveBeenLastCalledWith(WORKFLOW, { limit: 20, offset: 0, status }, expect.any(AbortSignal)))
  })

  it('paginates using offset and the returned total rather than fetching all records', async () => {
    mocks.getExecutionHistory.mockImplementation((_id: string, query: { offset: number }) => Promise.resolve(page([summary(`run-${query.offset}`)], 21, query.offset)))
    render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    await screen.findByText('1–1 of 21 executions')
    expect(screen.getByRole('button', { name: 'Previous page' }).hasAttribute('disabled')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await screen.findByText('21–21 of 21 executions')
    expect(mocks.getExecutionHistory).toHaveBeenLastCalledWith(WORKFLOW, { limit: 20, offset: 20 }, expect.any(AbortSignal))
    expect(screen.getByRole('button', { name: 'Next page' }).hasAttribute('disabled')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Previous page' }))
    await screen.findByText('1–1 of 21 executions')
  })

  it('refreshes manually and after the parent completes an execution, without polling', async () => {
    const { rerender } = render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    await screen.findByText('No executions yet.')
    expect(mocks.getExecutionHistory).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Refresh history' }))
    await waitFor(() => expect(mocks.getExecutionHistory).toHaveBeenCalledTimes(2))
    rerender(<ExecutionHistory workflowId={WORKFLOW} refreshKey={1} />)
    await waitFor(() => expect(mocks.getExecutionHistory).toHaveBeenCalledTimes(3))
  })

  it('returns to the last remaining page if retention shrinks the total during refresh', async () => {
    let shrunk = false
    mocks.getExecutionHistory.mockImplementation((_id: string, query: { offset: number }) => Promise.resolve(
      shrunk
        ? page(query.offset === 0 ? [summary('remaining-run')] : [], 1, query.offset)
        : page([summary(`run-${query.offset}`)], 21, query.offset),
    ))
    render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    await screen.findByText('1–1 of 21 executions')
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await screen.findByText('21–21 of 21 executions')
    shrunk = true
    fireEvent.click(screen.getByRole('button', { name: 'Refresh history' }))
    await screen.findByText('1–1 of 1 executions')
    expect(mocks.getExecutionHistory).toHaveBeenLastCalledWith(WORKFLOW, { limit: 20, offset: 0 }, expect.any(AbortSignal))
    expect(screen.getByRole('button', { name: 'View details remaining-run' })).toBeTruthy()
    expect(screen.queryByText(/21–20/)).toBeNull()
  })

  it('loads details independently and labels historical-version uncertainty', async () => {
    mocks.getExecutionHistory.mockResolvedValue(page([summary('run-1')]))
    render(<ExecutionHistory workflowId={WORKFLOW} workflowName="Saved workflow" refreshKey={0} />)
    fireEvent.click(await screen.findByRole('button', { name: 'View details run-1' }))
    const historical = await screen.findByRole('region', { name: 'Historical execution details' })
    expect(within(historical).getByText(/Canvas status is unchanged/)).toBeTruthy()
    expect(within(historical).getByText('Output not stored or unavailable.')).toBeTruthy()
    expect(mocks.getExecution).toHaveBeenCalledWith('run-1', expect.any(AbortSignal))
    fireEvent.click(screen.getByRole('button', { name: 'Close details' }))
    expect(screen.queryByRole('region', { name: 'Historical execution details' })).toBeNull()
  })

  it('shows an execution not-found error and supports retry', async () => {
    mocks.getExecutionHistory.mockResolvedValue(page([summary('missing')]))
    mocks.getExecution.mockRejectedValueOnce(new Error('Execution not found.')).mockResolvedValueOnce(detail('missing'))
    render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    fireEvent.click(await screen.findByRole('button', { name: 'View details missing' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Execution not found.')
    fireEvent.click(screen.getByRole('button', { name: 'Retry details' }))
    await screen.findByRole('region', { name: 'Historical execution details' })
  })

  it('keeps a failed history load separate from an empty history', async () => {
    mocks.getExecutionHistory.mockRejectedValue(new Error('Cannot reach the backend.'))
    render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    expect((await screen.findByRole('alert')).textContent).toContain('History load failed.')
    expect(screen.queryByText('No executions yet.')).toBeNull()
  })

  it('ignores old history responses after switching workflows', async () => {
    const old = deferred<ExecutionHistoryPage>()
    mocks.getExecutionHistory.mockReturnValueOnce(old.promise).mockResolvedValueOnce(page([summary('new-run', 'workflow-2')]))
    const { rerender } = render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    const oldSignal = mocks.getExecutionHistory.mock.calls[0][2] as AbortSignal
    rerender(<ExecutionHistory workflowId="workflow-2" refreshKey={0} />)
    await screen.findByRole('button', { name: 'View details new-run' })
    await act(async () => old.resolve(page([summary('old-run')])))
    expect(oldSignal.aborted).toBe(true)
    expect(screen.queryByRole('button', { name: 'View details old-run' })).toBeNull()
  })

  it('ignores obsolete detail responses and refuses a different workflow result', async () => {
    const first = deferred<ExecutionDetail>()
    mocks.getExecutionHistory.mockResolvedValue(page([summary('run-1'), summary('run-2')]))
    mocks.getExecution.mockReturnValueOnce(first.promise).mockResolvedValueOnce(detail('run-2'))
    render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    fireEvent.click(await screen.findByRole('button', { name: 'View details run-1' }))
    const firstSignal = mocks.getExecution.mock.calls[0][1] as AbortSignal
    fireEvent.click(screen.getByRole('button', { name: 'View details run-2' }))
    const details = await screen.findByRole('region', { name: 'Historical execution details' })
    expect(within(details).getByText('run-2')).toBeTruthy()
    await act(async () => first.resolve(detail('run-1')))
    expect(firstSignal.aborted).toBe(true)
    expect(within(details).queryByText('run-1')).toBeNull()
    mocks.getExecution.mockResolvedValue(detail('run-1', 'wrong-workflow'))
    fireEvent.click(screen.getByRole('button', { name: 'View details run-1' }))
    expect((await screen.findByRole('alert')).textContent).toContain('does not match this workflow')
  })

  it('cancels outstanding history requests when unmounted', () => {
    mocks.getExecutionHistory.mockReturnValue(new Promise(() => {}))
    const { unmount } = render(<ExecutionHistory workflowId={WORKFLOW} refreshKey={0} />)
    const signal = mocks.getExecutionHistory.mock.calls[0][2] as AbortSignal
    unmount()
    expect(signal.aborted).toBe(true)
  })
})
