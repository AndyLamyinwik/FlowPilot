import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { WorkflowCanvasProps } from '../components/workflow/WorkflowCanvas'
import type { NodeTypeMetadata, Workflow, WorkflowPayload } from '../types/workflow'
import WorkflowEditorPage from './WorkflowEditorPage'

const mocks = vi.hoisted(() => ({
  canvas: null as WorkflowCanvasProps | null,
  api: {
    getNodeTypes: vi.fn(), listWorkflows: vi.fn(), getWorkflow: vi.fn(),
    createWorkflow: vi.fn(), updateWorkflow: vi.fn(), deleteWorkflow: vi.fn(), validateWorkflow: vi.fn(),
  },
}))

vi.mock('../services/workflowApi', () => mocks.api)
vi.mock('../services/api', () => ({ getHealth: () => Promise.resolve({ status: 'ok' }) }))
vi.mock('../components/workflow/WorkflowCanvas', () => ({
  default: (props: WorkflowCanvasProps) => {
    mocks.canvas = props
    return <section aria-label="Mock workflow canvas">{props.nodes.map((node) => (
      <button key={node.id} type="button" data-testid={`select-${node.id}`}
        onClick={() => props.onSelectionChange({ nodes: [node], edges: [] })}>Select {node.data.name}</button>
    ))}</section>
  },
}))

const WORKFLOW_ID = '8a69a715-182d-4ba7-8a5f-d3c59842d4f3'
const OTHER_ID = '55ac7618-9891-46c4-ad98-54173aa52960'
const registry: NodeTypeMetadata[] = [
  { type: 'trigger.manual', display_name: 'Manual Trigger', category: 'trigger', description: 'Start manually' },
  { type: 'trigger.schedule', display_name: 'Schedule Trigger', category: 'trigger', description: 'Start on a cron schedule' },
  { type: 'action.http_request', display_name: 'HTTP Request', category: 'action', description: 'Make an HTTP request' },
  { type: 'logic.condition', display_name: 'Condition', category: 'logic', description: 'Choose a branch' },
  { type: 'data.transform', display_name: 'Transform', category: 'data', description: 'Map JSON fields' },
  { type: 'action.webhook', display_name: 'Webhook', category: 'action', description: 'Send an outgoing notification' },
  { type: 'utility.logger', display_name: 'Logger', category: 'utility', description: 'Record an execution event' },
]

function record(payload: WorkflowPayload, id = WORKFLOW_ID): Workflow {
  return structuredClone({ ...payload, id, created_at: '2026-10-28T01:00:00Z', updated_at: '2026-10-28T02:00:00Z' })
}

function saved(name = 'Saved Flow', id = WORKFLOW_ID): Workflow {
  return record({ name, description: 'An existing workflow', definition: {
    schema_version: 1,
    nodes: [{ id: 'saved-start', type: 'trigger.manual', name: 'Existing trigger', position: { x: 200, y: 160 }, config: { nested: { keep: true } } }],
    edges: [],
  } }, id)
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((fulfill, fail) => { resolve = fulfill; reject = fail })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.canvas = null
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
  mocks.api.getNodeTypes.mockResolvedValue(registry)
  mocks.api.listWorkflows.mockResolvedValue([])
  mocks.api.createWorkflow.mockImplementation(async (payload: WorkflowPayload) => record(payload))
  mocks.api.updateWorkflow.mockImplementation(async (_id: string, payload: WorkflowPayload) => record(payload))
  mocks.api.deleteWorkflow.mockResolvedValue(undefined)
  mocks.api.validateWorkflow.mockResolvedValue({ can_save: true, structural: { valid: true, errors: [], warnings: [] }, execution_readiness: { valid: true, errors: [], warnings: [] } })
})

async function editor() {
  render(<WorkflowEditorPage />)
  await screen.findByRole('button', { name: 'Add Manual Trigger' })
  await screen.findByText('Backend Connected')
}

function graph() {
  if (!mocks.canvas) throw new Error('Canvas is not mounted')
  return mocks.canvas
}

function add(type: string) {
  const metadata = registry.find((item) => item.type === type)!
  fireEvent.click(screen.getByRole('button', { name: `Add ${metadata.display_name}` }))
  return graph().nodes.at(-1)!
}

function rename(value: string) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Workflow name' }), { target: { value } })
}

async function save() {
  fireEvent.click(screen.getByRole('button', { name: 'Save Workflow' }))
  await screen.findByText('Saved', { exact: true })
}

async function open(workflow = saved()) {
  mocks.api.listWorkflows.mockResolvedValue([workflow])
  mocks.api.getWorkflow.mockResolvedValue(workflow)
  fireEvent.click(screen.getByRole('button', { name: 'Open Workflow' }))
  fireEvent.click(await screen.findByRole('button', { name: new RegExp(workflow.name) }))
  await waitFor(() => expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe(workflow.name))
}

describe('workflow editor persistence and controlled state', () => {
  it('saves a legal empty draft only after the explicit Save action', async () => {
    await editor()
    expect(mocks.api.createWorkflow).not.toHaveBeenCalled()
    expect(screen.getByText('Unsaved Changes', { exact: true })).toBeTruthy()
    await save()
    expect(mocks.api.createWorkflow).toHaveBeenCalledWith({
      name: 'Untitled Workflow', description: '', definition: { schema_version: 1, nodes: [], edges: [] },
    }, expect.any(AbortSignal))
  })

  it('creates nodes, configures HTTP and saves the connected graph without autosaving', async () => {
    await editor()
    const start = add('trigger.manual')
    const http = add('action.http_request')
    rename('My HTTP draft')
    fireEvent.change(screen.getByRole('textbox', { name: 'Node name' }), { target: { value: 'Fetch JSON' } })
    fireEvent.change(screen.getByRole('textbox', { name: 'URL' }), { target: { value: 'https://example.com/data' } })
    act(() => graph().onConnect({ source: start.id, target: http.id, sourceHandle: null, targetHandle: null }))
    expect(mocks.api.createWorkflow).not.toHaveBeenCalled()
    await save()
    const payload = mocks.api.createWorkflow.mock.calls[0][0] as WorkflowPayload
    expect(payload.name).toBe('My HTTP draft')
    expect(payload.definition.nodes[1]).toMatchObject({ id: http.id, type: 'action.http_request', name: 'Fetch JSON', config: { method: 'GET', url: 'https://example.com/data', timeout: 10 } })
    expect(payload.definition.edges).toEqual([{ id: expect.any(String), source: start.id, target: http.id, source_handle: null, target_handle: null }])
    expect(payload.definition.nodes[0].id).not.toBe(payload.definition.nodes[1].id)
    expect(payload.definition.nodes[1]).not.toHaveProperty('data')
  })

  it('saves unfinished HTTP config as a Draft instead of enforcing execution readiness', async () => {
    await editor()
    add('action.http_request')
    await save()
    expect((mocks.api.createWorkflow.mock.calls[0][0] as WorkflowPayload).definition.nodes[0].config.url).toBe('')
  })

  it('opens saved nodes with configuration and positions, then updates the same workflow', async () => {
    await editor()
    const workflow = saved()
    await open(workflow)
    expect(graph().nodes[0].position).toEqual({ x: 200, y: 160 })
    expect(graph().nodes[0].data.config).toEqual({ nested: { keep: true } })
    expect(screen.getByText('Saved', { exact: true })).toBeTruthy()
    rename('Renamed workflow')
    await save()
    expect(mocks.api.createWorkflow).not.toHaveBeenCalled()
    expect(mocks.api.updateWorkflow).toHaveBeenCalledWith(WORKFLOW_ID, expect.objectContaining({ name: 'Renamed workflow' }), expect.any(AbortSignal))
  })

  it('persists distinct Condition true and false handle IDs', async () => {
    await editor()
    const condition = add('logic.condition')
    const yes = add('utility.logger')
    const no = add('utility.logger')
    act(() => graph().onConnect({ source: condition.id, target: yes.id, sourceHandle: 'true', targetHandle: null }))
    act(() => graph().onConnect({ source: condition.id, target: no.id, sourceHandle: 'false', targetHandle: null }))
    await save()
    const edges = (mocks.api.createWorkflow.mock.calls[0][0] as WorkflowPayload).definition.edges
    expect(edges.map((edge) => [edge.target, edge.source_handle])).toEqual([[yes.id, 'true'], [no.id, 'false']])
  })

  it('rejects invalid connections visibly without changing the graph', async () => {
    await editor()
    const start = add('trigger.manual')
    act(() => graph().onConnect({ source: start.id, target: start.id, sourceHandle: null, targetHandle: null }))
    expect(screen.getByRole('alert').textContent).toContain('cannot connect to itself')
    expect(graph().edges).toHaveLength(0)
  })

  it('selection changes do not mark a saved graph dirty, while moving a node does', async () => {
    await editor()
    await open()
    const node = graph().nodes[0]
    act(() => graph().onSelectionChange({ nodes: [node], edges: [] }))
    act(() => graph().onNodesChange([{ id: node.id, type: 'select', selected: true }]))
    act(() => graph().onNodesChange([{ id: node.id, type: 'dimensions', dimensions: { width: 220, height: 140 } }]))
    expect(screen.getByText('Saved', { exact: true })).toBeTruthy()
    act(() => graph().onNodesChange([{ id: node.id, type: 'position', position: { x: 320, y: 200 }, dragging: false }]))
    expect(screen.getByText('Unsaved Changes', { exact: true })).toBeTruthy()
    expect(graph().nodes[0].position).toEqual({ x: 320, y: 200 })
    expect(mocks.api.updateWorkflow).not.toHaveBeenCalled()
  })

  it('deleting a node removes its connected edges before saving', async () => {
    await editor()
    const start = add('trigger.manual')
    const logger = add('utility.logger')
    act(() => graph().onConnect({ source: start.id, target: logger.id, sourceHandle: null, targetHandle: null }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete node' }))
    expect(graph().nodes.map((node) => node.id)).toEqual([start.id])
    expect(graph().edges).toHaveLength(0)
    await save()
    expect((mocks.api.createWorkflow.mock.calls[0][0] as WorkflowPayload).definition.edges).toEqual([])
  })

  it('deleting a selected edge marks the graph dirty without deleting nodes', async () => {
    await editor()
    const start = add('trigger.manual')
    const logger = add('utility.logger')
    act(() => graph().onConnect({ source: start.id, target: logger.id, sourceHandle: null, targetHandle: null }))
    await save()
    const edge = graph().edges[0]
    act(() => graph().onEdgesChange([{ id: edge.id, type: 'select', selected: true }]))
    expect(screen.getByText('Saved', { exact: true })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Delete selected connection' }))
    expect(graph().edges).toHaveLength(0)
    expect(graph().nodes).toHaveLength(2)
    expect(screen.getByText('Unsaved Changes', { exact: true })).toBeTruthy()
  })

  it('retains invalid JSON across selection changes and blocks saving stale valid config', async () => {
    await editor()
    const transform = add('data.transform')
    const invalid = '{"mapping":'
    fireEvent.change(screen.getByRole('textbox', { name: 'Mapping configuration (JSON)' }), { target: { value: invalid } })
    const logger = add('utility.logger')
    expect(graph().nodes.at(-1)?.id).toBe(logger.id)
    fireEvent.click(screen.getByTestId(`select-${transform.id}`))
    expect((screen.getByRole('textbox', { name: 'Mapping configuration (JSON)' }) as HTMLTextAreaElement).value).toBe(invalid)
    fireEvent.click(screen.getByRole('button', { name: 'Save Workflow' }))
    expect(mocks.api.createWorkflow).not.toHaveBeenCalled()
    expect(screen.getByText('Save Failed', { exact: true })).toBeTruthy()
    expect(screen.getAllByRole('alert').some((item) => item.textContent?.includes('input has been kept'))).toBe(true)
    fireEvent.change(screen.getByRole('textbox', { name: 'Mapping configuration (JSON)' }), { target: { value: '{"mapping":{"source":{"value":"FlowPilot"}}}' } })
    await save()
    expect((mocks.api.createWorkflow.mock.calls[0][0] as WorkflowPayload).definition.nodes[0].config).toEqual({ mapping: { source: { value: 'FlowPilot' } } })
  })

  it('prevents forbidden headers from being saved, including after changing selection', async () => {
    await editor()
    const http = add('action.http_request')
    fireEvent.change(screen.getByRole('textbox', { name: 'Headers (JSON)' }), { target: { value: '{"Authorization":"secret-value"}' } })
    add('utility.logger')
    fireEvent.click(screen.getByRole('button', { name: 'Save Workflow' }))
    expect(mocks.api.createWorkflow).not.toHaveBeenCalled()
    expect(graph().nodes.find((node) => node.id === http.id)?.data.config.headers).toEqual({})
    expect(screen.getByText('Save Failed', { exact: true })).toBeTruthy()
  })

  it('does not let deleted invalid JSON buffers block a later valid save', async () => {
    await editor()
    add('data.transform')
    fireEvent.change(screen.getByRole('textbox', { name: 'Mapping configuration (JSON)' }), { target: { value: '{' } })
    fireEvent.click(screen.getByRole('button', { name: 'Delete node' }))
    await save()
    expect((mocks.api.createWorkflow.mock.calls[0][0] as WorkflowPayload).definition.nodes).toEqual([])
  })

  it('keeps edits made during an in-flight save and updates them on the next save', async () => {
    await editor()
    const pending = deferred<Workflow>()
    mocks.api.createWorkflow.mockReturnValueOnce(pending.promise)
    rename('First revision')
    fireEvent.click(screen.getByRole('button', { name: 'Save Workflow' }))
    expect(screen.getByText('Saving', { exact: true })).toBeTruthy()
    rename('Second revision')
    const snapshot = mocks.api.createWorkflow.mock.calls[0][0] as WorkflowPayload
    await act(async () => pending.resolve(record(snapshot)))
    expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe('Second revision')
    expect(screen.getByText('Unsaved Changes', { exact: true })).toBeTruthy()
    await save()
    expect(mocks.api.updateWorkflow).toHaveBeenCalledWith(WORKFLOW_ID, expect.objectContaining({ name: 'Second revision' }), expect.any(AbortSignal))
  })

  it('keeps the latest node and edge selection when an unchanged save finishes', async () => {
    await editor()
    const start = add('trigger.manual')
    const logger = add('utility.logger')
    act(() => graph().onConnect({ source: start.id, target: logger.id, sourceHandle: null, targetHandle: null }))
    await save()
    act(() => {
      graph().onNodesChange([{ type: 'select', id: start.id, selected: true }, { type: 'select', id: logger.id, selected: false }])
      graph().onSelectionChange({ nodes: [graph().nodes.find((node) => node.id === start.id)!], edges: [] })
    })
    const pending = deferred<Workflow>()
    mocks.api.updateWorkflow.mockReturnValueOnce(pending.promise)
    fireEvent.click(screen.getByRole('button', { name: 'Save Workflow' }))
    const edge = graph().edges[0]
    act(() => {
      graph().onNodesChange([{ type: 'select', id: start.id, selected: false }, { type: 'select', id: logger.id, selected: true }])
      graph().onEdgesChange([{ type: 'select', id: edge.id, selected: true }])
      graph().onSelectionChange({ nodes: [graph().nodes.find((node) => node.id === logger.id)!], edges: [edge] })
    })
    await act(async () => pending.resolve(record(mocks.api.updateWorkflow.mock.calls[0][1] as WorkflowPayload)))
    expect(graph().nodes.filter((node) => node.selected).map((node) => node.id)).toEqual([logger.id])
    expect(graph().edges.find((item) => item.id === edge.id)?.selected).toBe(true)
    expect((screen.getByRole('textbox', { name: 'Node name' }) as HTMLInputElement).value).toBe('Logger')
    expect(screen.getByText('Saved', { exact: true })).toBeTruthy()
  })

  it('warns about unsupported loaded handles and preserves them on the next Draft save', async () => {
    await editor()
    const workflow = saved('Workflow with future ports')
    workflow.definition.nodes.push({ id: 'future-target', type: 'utility.logger', name: 'Future port consumer', position: { x: 500, y: 160 }, config: {} })
    workflow.definition.edges.push({ id: 'future-edge', source: 'saved-start', target: 'future-target', source_handle: 'legacy-output', target_handle: 'future-input' })
    await open(workflow)
    expect(await screen.findByText(/unsupported handles/i)).toBeTruthy()
    expect(graph().edges[0]).toMatchObject({ id: 'future-edge', sourceHandle: 'legacy-output', targetHandle: 'future-input' })
    await save()
    expect((mocks.api.updateWorkflow.mock.calls[0][1] as WorkflowPayload).definition.edges).toEqual(workflow.definition.edges)
  })

  it('asks before discarding edits for a new workflow and supports cancel', async () => {
    await editor()
    rename('Keep this draft')
    fireEvent.click(screen.getByRole('button', { name: 'New Workflow' }))
    expect(screen.getByRole('dialog', { name: 'Discard unsaved changes?' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe('Keep this draft')
    fireEvent.click(screen.getByRole('button', { name: 'New Workflow' }))
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe('Untitled Workflow')
    expect(graph().nodes).toHaveLength(0)
  })

  it('asks before replacing unsaved changes when opening another workflow', async () => {
    await editor()
    rename('Unsaved draft')
    const workflow = saved('Other saved flow', OTHER_ID)
    mocks.api.listWorkflows.mockResolvedValue([workflow])
    mocks.api.getWorkflow.mockResolvedValue(workflow)
    fireEvent.click(screen.getByRole('button', { name: 'Open Workflow' }))
    fireEvent.click(await screen.findByRole('button', { name: /Other saved flow/ }))
    expect(mocks.api.getWorkflow).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Discard changes' }))
    await waitFor(() => expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe(workflow.name))
    expect(mocks.api.getWorkflow).toHaveBeenCalledWith(OTHER_ID, expect.any(AbortSignal))
  })

  it('does not discard edits made while an open request is in flight', async () => {
    await editor()
    const pending = deferred<Workflow>()
    const workflow = saved()
    mocks.api.listWorkflows.mockResolvedValue([workflow])
    mocks.api.getWorkflow.mockReturnValueOnce(pending.promise)
    fireEvent.click(screen.getByRole('button', { name: 'Open Workflow' }))
    fireEvent.click(await screen.findByRole('button', { name: /Saved Flow/ }))
    rename('Editing continued')
    await act(async () => pending.resolve(workflow))
    expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe('Editing continued')
    expect(screen.getByText('Unsaved Changes', { exact: true })).toBeTruthy()
  })

  it('confirms workflow deletion and shows a 409 reason without resetting the graph', async () => {
    await editor()
    await open()
    mocks.api.deleteWorkflow.mockRejectedValueOnce(new Error('This workflow has an active execution. Wait for it to finish before deleting.'))
    fireEvent.click(screen.getByRole('button', { name: 'Delete Workflow' }))
    expect(mocks.api.deleteWorkflow).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog', { name: 'Delete workflow?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete workflow' }))
    expect((await screen.findByRole('alert')).textContent).toContain('active execution')
    expect(graph().nodes).toHaveLength(1)
    expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe('Saved Flow')
    fireEvent.click(screen.getByRole('button', { name: 'Delete Workflow' }))
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Delete workflow?' })).getByRole('button', { name: 'Delete workflow' }))
    await waitFor(() => expect(graph().nodes).toHaveLength(0))
    expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe('Untitled Workflow')
  })

  it('reports save failures while retaining all local nodes and input', async () => {
    await editor()
    add('utility.logger')
    rename('Preserved draft')
    mocks.api.createWorkflow.mockRejectedValueOnce(new Error('Cannot reach the backend. Check your connection and try again.'))
    fireEvent.click(screen.getByRole('button', { name: 'Save Workflow' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Cannot reach the backend')
    expect(screen.getByText('Save Failed', { exact: true })).toBeTruthy()
    expect(graph().nodes).toHaveLength(1)
    expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe('Preserved draft')
    await save()
  })

  it('reports load failures without changing the current workflow', async () => {
    await editor()
    await open()
    const other = saved('Deleted workflow', OTHER_ID)
    mocks.api.listWorkflows.mockResolvedValue([other])
    mocks.api.getWorkflow.mockRejectedValueOnce(new Error('Workflow not found. It may have been deleted.'))
    fireEvent.click(screen.getByRole('button', { name: 'Open Workflow' }))
    fireEvent.click(await screen.findByRole('button', { name: /Deleted workflow/ }))
    expect((await screen.findByRole('alert')).textContent).toContain('Workflow not found')
    expect(graph().nodes[0].id).toBe('saved-start')
    expect((screen.getByRole('textbox', { name: 'Workflow name' }) as HTMLInputElement).value).toBe('Saved Flow')
  })

  it('shows offline registry failure and retries without inventing available nodes', async () => {
    mocks.api.getNodeTypes.mockRejectedValueOnce(new Error('Cannot reach the backend.'))
    render(<WorkflowEditorPage />)
    expect((await screen.findByRole('alert')).textContent).toContain('Cannot reach the backend')
    expect(screen.queryByRole('button', { name: 'Add Manual Trigger' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Retry node library' }))
    await screen.findByRole('button', { name: 'Add Manual Trigger' })
  })

  it('warns before leaving only when meaningful edits are unsaved', async () => {
    await editor()
    await open()
    const clean = new Event('beforeunload', { cancelable: true })
    fireEvent(window, clean)
    expect(clean.defaultPrevented).toBe(false)
    rename('Changed name')
    const dirty = new Event('beforeunload', { cancelable: true })
    fireEvent(window, dirty)
    expect(dirty.defaultPrevented).toBe(true)
  })

  it('validates a saved graph and does not treat validation as execution', async () => {
    await editor()
    await open()
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    await screen.findByText(/Saved graph is valid/)
    expect(mocks.api.validateWorkflow).toHaveBeenCalledWith(WORKFLOW_ID, expect.any(AbortSignal))
    rename('Unsaved changed graph')
    fireEvent.click(screen.getByRole('button', { name: 'Validate' }))
    expect(screen.getByText('Save your changes before validating the saved workflow.')).toBeTruthy()
    expect(mocks.api.validateWorkflow).toHaveBeenCalledOnce()
  })
})
