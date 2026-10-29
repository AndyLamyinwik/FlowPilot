import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { WorkflowCanvasProps } from '../components/workflow/WorkflowCanvas'
import type { ExecutionDetail, ExecutionResult } from '../types/execution'
import type { NodeTypeMetadata, Workflow, WorkflowValidationReport } from '../types/workflow'
import { ApiError } from '../services/workflowApi'
import WorkflowEditorPage from './WorkflowEditorPage'

const mocks = vi.hoisted(() => ({
  canvas: null as WorkflowCanvasProps | null,
  api: { getNodeTypes: vi.fn(), listWorkflows: vi.fn(), getWorkflow: vi.fn(), createWorkflow: vi.fn(), updateWorkflow: vi.fn(), deleteWorkflow: vi.fn(), validateWorkflow: vi.fn() },
  execution: { executeWorkflow: vi.fn(), getExecutionHistory: vi.fn(), getExecution: vi.fn() },
}))
vi.mock('../services/workflowApi', async importOriginal => ({ ...await importOriginal<typeof import('../services/workflowApi')>(), ...mocks.api }))
vi.mock('../services/executionApi', () => mocks.execution)
vi.mock('../services/api', () => ({ getHealth: () => Promise.resolve({ status: 'ok' }), getApiBaseUrl: () => '/api' }))
vi.mock('../components/schedule/SchedulePanel', () => ({ default: () => <div>Schedule panel</div> }))
vi.mock('../components/workflow/WorkflowCanvas', () => ({ default: (props: WorkflowCanvasProps) => {
  mocks.canvas = props
  return <section aria-label="Mock canvas">{props.nodes.map(node => <button key={node.id} type="button" onClick={() => props.onSelectionChange({ nodes: [node], edges: [] })}>Select {node.data.name}</button>)}</section>
} }))

const ID = '8a69a715-182d-4ba7-8a5f-d3c59842d4f3'
const OTHER_ID = '55ac7618-9891-46c4-ad98-54173aa52960'
const EXECUTION = '382345e2-1d6e-4cf7-bd27-b669c4105ac9'
const TIME = '2026-10-29T09:00:00Z'
const registry: NodeTypeMetadata[] = [
  { type: 'trigger.manual', display_name: 'Manual Trigger', category: 'trigger', description: 'Manual' },
  { type: 'trigger.schedule', display_name: 'Schedule Trigger', category: 'trigger', description: 'Schedule' },
  { type: 'utility.logger', display_name: 'Logger', category: 'utility', description: 'Logger' },
]
function workflow(id = ID, type = 'trigger.manual'): Workflow {
  return { id, name: id === ID ? 'Saved workflow' : 'Other workflow', description: null, created_at: TIME, updated_at: TIME,
    definition: { schema_version: 1, nodes: [
      { id: 'start', type, name: 'Start', position: { x: 0, y: 0 }, config: type === 'trigger.schedule' ? { cron: '0 9 * * *', timezone: 'UTC' } : {} },
      { id: 'left', type: 'utility.logger', name: 'Logger', position: { x: 100, y: 0 }, config: {} },
      { id: 'right', type: 'utility.logger', name: 'Logger', position: { x: 100, y: 100 }, config: {} },
    ], edges: [{ id: 'left', source: 'start', target: 'left' }, { id: 'right', source: 'start', target: 'right' }] } }
}
function execution(status = 'success', workflowId = ID): ExecutionResult {
  return { execution_id: EXECUTION, workflow_id: workflowId, status, started_at: TIME, finished_at: TIME, error: status === 'failed' ? { code: 'NODE_EXECUTION_FAILED', message: 'Private traceback', node_id: 'left' } : null,
    node_results: ['right', 'start', 'left'].map(id => ({ node_id: id, status: id === 'right' ? 'skipped' : status,
      started_at: TIME, finished_at: TIME, duration_ms: 0, output: { id }, error: null })) }
}
function report(valid = true): WorkflowValidationReport {
  return { can_save: true, structural: { valid: true, errors: [], warnings: [] }, execution_readiness: { valid, errors: valid ? [] : [{ code: 'MISSING_TRIGGER', message: 'Missing trigger', node_id: 'start' }], warnings: [] } }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((a, b) => { resolve = a; reject = b })
  return { promise, resolve, reject }
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
  mocks.canvas = null
  mocks.api.getNodeTypes.mockResolvedValue(registry)
  mocks.api.listWorkflows.mockResolvedValue([workflow(), workflow(OTHER_ID)])
  mocks.api.getWorkflow.mockImplementation(async (id: string) => workflow(id))
  mocks.api.validateWorkflow.mockResolvedValue(report())
  mocks.api.createWorkflow.mockImplementation(async (payload: Omit<Workflow, 'id' | 'created_at' | 'updated_at'>) => ({ ...payload, id: ID, created_at: TIME, updated_at: TIME }))
  mocks.api.updateWorkflow.mockImplementation(async (_id: string, payload: Omit<Workflow, 'id' | 'created_at' | 'updated_at'>) => ({ ...payload, id: ID, created_at: TIME, updated_at: TIME }))
  mocks.execution.executeWorkflow.mockResolvedValue(execution())
  mocks.execution.getExecutionHistory.mockResolvedValue({ items: [], limit: 20, offset: 0, total: 0 })
})
async function editor(saved = true) {
  render(<WorkflowEditorPage />)
  await screen.findByRole('button', { name: 'Add Manual Trigger' })
  if (saved) await open(ID)
}
async function open(id: string) {
  fireEvent.click(screen.getByRole('button', { name: 'Open Workflow' }))
  fireEvent.click(await screen.findByRole('button', { name: new RegExp(id === ID ? 'Saved workflow' : 'Other workflow') }))
  await waitFor(() => expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe(id === ID ? 'Saved workflow' : 'Other workflow'))
  await screen.findByText('Saved', { exact: true })
  await waitFor(() => expect(screen.getByRole('button', { name: 'Run Workflow' }).hasAttribute('disabled')).toBe(false))
}
const run = () => fireEvent.click(screen.getByRole('button', { name: 'Run Workflow' }))
const canvas = () => { if (!mocks.canvas) throw new Error('Canvas unavailable'); return mocks.canvas }

describe('saved workflow execution integration', () => {
  it('keeps registry presentation metadata when a direct editor load resolves in the same batch', async () => {
    mocks.api.getNodeTypes.mockResolvedValue(registry)
    mocks.api.getWorkflow.mockResolvedValue(workflow())
    render(<WorkflowEditorPage initialWorkflowId={ID} />)
    await screen.findByText('Saved', { exact: true })
    expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe('Saved workflow')
    expect(canvas().nodes.find(node => node.id === 'start')?.data).toMatchObject({
      name: 'Start', nodeType: 'trigger.manual', metadata: { display_name: 'Manual Trigger', description: 'Manual', category: 'trigger' },
    })
    expect(canvas().nodes.find(node => node.id === 'left')?.data.metadata?.description).toBe('Logger')
    expect(mocks.api.getWorkflow).toHaveBeenCalledWith(ID, expect.any(AbortSignal))
    expect(mocks.api.createWorkflow).not.toHaveBeenCalled()
  })

  it('shows Run and blocks an unsaved workflow without issuing validation or execution requests', async () => {
    await editor(false)
    run()
    expect(screen.getByText('You have unsaved changes. Save your workflow before running.')).toBeTruthy()
    expect(mocks.api.validateWorkflow).not.toHaveBeenCalled()
    expect(mocks.execution.executeWorkflow).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Save Workflow' }).hasAttribute('disabled')).toBe(false)
  })

  it('blocks dirty saved data instead of running the older backend version', async () => {
    await editor()
    fireEvent.change(screen.getByRole('textbox', { name: 'Workflow name' }), { target: { value: 'Unsaved name' } })
    run()
    expect(screen.getByText('You have unsaved changes. Save your workflow before running.')).toBeTruthy()
    expect(mocks.execution.executeWorkflow).not.toHaveBeenCalled()
  })

  it('validates a saved manual workflow then executes and maps every result using node ID', async () => {
    await editor()
    run()
    await screen.findByText(EXECUTION)
    expect(mocks.api.validateWorkflow).toHaveBeenCalledWith(ID, expect.any(AbortSignal))
    expect(mocks.execution.executeWorkflow).toHaveBeenCalledWith(ID, expect.any(AbortSignal))
    expect(canvas().nodes.map(node => [node.id, node.data.executionStatus])).toEqual([['start', 'success'], ['left', 'success'], ['right', 'skipped']])
    expect(canvas().nodes.every(node => node.data.executionId === EXECUTION)).toBe(true)
  })

  it('does not treat a Schedule Trigger workflow as a manual workflow', async () => {
    mocks.api.getWorkflow.mockResolvedValue(workflow(ID, 'trigger.schedule'))
    await editor()
    run()
    expect(screen.getByText('This workflow runs on a schedule.')).toBeTruthy()
    expect(mocks.execution.executeWorkflow).not.toHaveBeenCalled()
  })

  it('blocks a draft without a manual trigger without preventing Save Draft', async () => {
    const draft = workflow()
    draft.definition.nodes = draft.definition.nodes.filter(node => node.type !== 'trigger.manual')
    draft.definition.edges = []
    mocks.api.getWorkflow.mockResolvedValue(draft)
    await editor()
    run()
    expect(screen.getByText(/requires exactly one Manual Trigger/)).toBeTruthy()
    expect(mocks.execution.executeWorkflow).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Save Workflow' }))
    await waitFor(() => expect(mocks.api.updateWorkflow).toHaveBeenCalled())
  })

  it('prevents repeated Run while the synchronous request is still pending without fake node animation', async () => {
    const pending = deferred<ExecutionResult>()
    mocks.execution.executeWorkflow.mockReturnValue(pending.promise)
    await editor()
    run()
    await waitFor(() => expect(mocks.execution.executeWorkflow).toHaveBeenCalledTimes(1))
    const running = screen.getByRole('button', { name: /Running/ })
    expect(running.hasAttribute('disabled')).toBe(true)
    fireEvent.click(running)
    expect(mocks.execution.executeWorkflow).toHaveBeenCalledTimes(1)
    expect(canvas().nodes.every(node => node.data.executionStatus === undefined)).toBe(true)
    await act(async () => pending.resolve(execution()))
    await screen.findByText(EXECUTION)
  })

  it('shows an HTTP 200 failed execution as Failed rather than a network failure', async () => {
    mocks.execution.executeWorkflow.mockResolvedValue(execution('failed'))
    await editor()
    run()
    await screen.findByText(EXECUTION)
    expect(canvas().nodes.find(node => node.id === 'left')?.data.executionStatus).toBe('failed')
    expect(screen.queryByText(/Execution outcome is unknown/)).toBeNull()
    expect(screen.queryByText('Private traceback')).toBeNull()
  })

  it('shows a clear 409 conflict without fabricating execution success', async () => {
    mocks.execution.executeWorkflow.mockRejectedValue(new ApiError(409, 'Workflow is already running.'))
    await editor()
    run()
    await screen.findByText('Workflow is already running.')
    expect(screen.queryByText(EXECUTION)).toBeNull()
    expect(canvas().nodes.every(node => node.data.executionStatus === undefined)).toBe(true)
  })

  it('surfaces strict Execute 422 issues with node-location actions', async () => {
    const error = new ApiError(422, 'Workflow validation failed.', [{ code: 'INVALID_NODE_CONFIG', message: 'Node configuration invalid', node_id: 'left' }])
    mocks.execution.executeWorkflow.mockRejectedValue(error)
    await editor()
    run()
    await screen.findByRole('button', { name: 'Locate node left' })
    fireEvent.click(screen.getByRole('button', { name: 'Locate node left' }))
    expect(canvas().nodes.find(node => node.id === 'left')?.selected).toBe(true)
    expect(screen.getByText('Validation Failed')).toBeTruthy()
  })

  it('does not execute after general graph validation fails', async () => {
    mocks.api.validateWorkflow.mockResolvedValue(report(false))
    await editor()
    run()
    await screen.findByText('Workflow validation failed. Review the errors in Validation.')
    expect(mocks.execution.executeWorkflow).not.toHaveBeenCalled()
  })

  it('handles an uncertain request outcome without claiming the workflow failed', async () => {
    mocks.execution.executeWorkflow.mockRejectedValue(new ApiError(null, 'Cannot reach the backend.'))
    await editor()
    run()
    await screen.findByText(/Execution outcome is unknown/)
    expect(screen.getByText(/Check execution history before trying again/)).toBeTruthy()
    expect(canvas().nodes.every(node => node.data.executionStatus === undefined)).toBe(true)
  })

  it('clears current-version badges after editing while retaining a clearly marked previous result', async () => {
    await editor()
    run()
    await screen.findByText(EXECUTION)
    fireEvent.change(screen.getByRole('textbox', { name: 'Workflow name' }), { target: { value: 'Changed after run' } })
    expect(canvas().nodes.every(node => node.data.executionStatus === undefined)).toBe(true)
    expect(screen.getByText(/Workflow changed since this execution/)).toBeTruthy()
    expect(screen.getByText(EXECUTION)).toBeTruthy()
  })

  it('ignores a previous workflow response after a new workflow has been opened', async () => {
    const pending = deferred<ExecutionResult>()
    mocks.execution.executeWorkflow.mockReturnValue(pending.promise)
    await editor()
    run()
    await waitFor(() => expect(mocks.execution.executeWorkflow).toHaveBeenCalled())
    const signal = mocks.execution.executeWorkflow.mock.calls[0][1] as AbortSignal
    await open(OTHER_ID)
    await act(async () => pending.resolve(execution()))
    expect(signal.aborted).toBe(true)
    expect(screen.queryByText(EXECUTION)).toBeNull()
    expect(canvas().nodes.every(node => node.data.executionStatus === undefined)).toBe(true)
  })

  it('refreshes visited history after an execution and does not apply historical results to the canvas', async () => {
    await editor()
    fireEvent.click(screen.getByRole('button', { name: 'History' }))
    await screen.findByText('No executions yet.')
    expect(mocks.execution.getExecutionHistory).toHaveBeenCalledTimes(1)
    run()
    await screen.findByText(EXECUTION)
    await waitFor(() => expect(mocks.execution.getExecutionHistory).toHaveBeenCalledTimes(2))
    const badges = canvas().nodes.map(node => node.data.executionStatus)
    const historicalId = 'historical-run'
    mocks.execution.getExecutionHistory.mockResolvedValue({ items: [{ execution_id: historicalId, workflow_id: ID, trigger_type: 'schedule', status: 'failed', started_at: TIME, finished_at: TIME, duration_ms: 10 }], limit: 20, offset: 0, total: 1 })
    const historyDetail: ExecutionDetail = { ...execution('failed'), execution_id: historicalId, trigger_type: 'schedule', duration_ms: 10, created_at: TIME, definition_hash: 'different', outputs_stored: false, history_truncated: false }
    mocks.execution.getExecution.mockResolvedValue(historyDetail)
    fireEvent.click(screen.getByRole('button', { name: 'History' }))
    fireEvent.click(screen.getByRole('button', { name: 'Refresh history' }))
    fireEvent.click(await screen.findByRole('button', { name: `View details ${historicalId}` }))
    const historical = await screen.findByRole('region', { name: 'Historical execution details' })
    expect(within(historical).getByText(/Canvas status is unchanged/)).toBeTruthy()
    expect(canvas().nodes.map(node => node.data.executionStatus)).toEqual(badges)
  })

  it('does not start execution if editing continues while validation is pending', async () => {
    const validation = deferred<WorkflowValidationReport>()
    mocks.api.validateWorkflow.mockReturnValue(validation.promise)
    await editor()
    run()
    fireEvent.change(screen.getByRole('textbox', { name: 'Workflow name' }), { target: { value: 'Changed during validation' } })
    await act(async () => validation.resolve(report()))
    expect(mocks.execution.executeWorkflow).not.toHaveBeenCalled()
    expect(screen.getByText(/Workflow changed during validation/)).toBeTruthy()
  })
})
