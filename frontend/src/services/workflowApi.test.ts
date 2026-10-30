import { describe, expect, it, vi } from 'vitest'
import type { Workflow, WorkflowPayload } from '../types/workflow'
import {
  ApiError, createWorkflow, deleteWorkflow, getNodeTypes, getWorkflow, listWorkflows,
  updateWorkflow, validateWorkflow,
} from './workflowApi'

const payload: WorkflowPayload = { name: 'Draft', description: '', definition: { schema_version: 1, nodes: [], edges: [] } }
const workflow: Workflow = {
  ...payload, id: 'e3fce261-4bc7-4bd6-9a7c-b33eaaaf10f0',
  created_at: '2026-10-28T00:00:00Z', updated_at: '2026-10-28T00:00:00Z',
}
const response = (data: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(data), { status })

describe('workflow API client', () => {
  it('uses the configured API base and sends exact create and full update schema', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(response(workflow)))
    vi.stubGlobal('fetch', fetch)
    vi.stubEnv('VITE_API_BASE_URL', 'https://flowpilot.example/api///')
    await expect(createWorkflow(payload)).resolves.toEqual(workflow)
    await expect(updateWorkflow(workflow.id, payload)).resolves.toEqual(workflow)
    expect(fetch.mock.calls[0][0]).toBe('https://flowpilot.example/api/workflows')
    expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'POST', body: JSON.stringify(payload), headers: { Accept: 'application/json', 'Content-Type': 'application/json' } })
    expect(fetch.mock.calls[1][0]).toBe(`https://flowpilot.example/api/workflows/${workflow.id}`)
    expect(fetch.mock.calls[1][1].method).toBe('PUT')
  })

  it('lists and reloads saved workflow data without changing unknown config or handles', async () => {
    const item: Workflow = { ...workflow, definition: {
      schema_version: 1,
      nodes: [{ id: 'future', type: 'custom.future', name: 'Future', position: { x: 1.5, y: -4 }, config: { custom: { unknown: false } } }], edges: [],
    } }
    const fetch = vi.fn().mockResolvedValueOnce(response([item])).mockResolvedValueOnce(response(item))
    vi.stubGlobal('fetch', fetch)
    await expect(listWorkflows()).resolves.toEqual([{ ...item, definition: {
      schema_version: 1, nodes: [{ id: 'future', type: 'custom.future', name: 'Future' }], edges: [],
    } }])
    await expect(getWorkflow(workflow.id)).resolves.toEqual(item)
    expect(fetch.mock.calls[0][0]).toBe('/api/workflows')
    expect(fetch.mock.calls[1][0]).toBe(`/api/workflows/${workflow.id}`)
  })

  it('accepts delete204 without trying to read a JSON body', async () => {
    const fetch = vi.fn().mockResolvedValue(response(null, 204))
    vi.stubGlobal('fetch', fetch)
    await expect(deleteWorkflow(workflow.id)).resolves.toBeUndefined()
    expect(fetch.mock.calls[0][1].method).toBe('DELETE')
  })

  it('loads registry metadata instead of inventing unavailable node types', async () => {
    const registry = [{ type: 'custom.future', display_name: 'Future', category: 'data', description: 'From backend' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(registry)))
    await expect(getNodeTypes()).resolves.toEqual(registry)
  })

  it('reads structural and general readiness validation without conflating them', async () => {
    const report = {
      can_save: true, structural: { valid: true, errors: [], warnings: [] },
      execution_readiness: { valid: false, errors: [{ code: 'MISSING_TRIGGER', message: 'Workflow requires a trigger node', node_id: null, edge_id: null }], warnings: [] },
    }
    const fetch = vi.fn().mockResolvedValue(response(report))
    vi.stubGlobal('fetch', fetch)
    await expect(validateWorkflow(workflow.id)).resolves.toEqual(report)
    expect(fetch.mock.calls[0][0]).toBe(`/api/workflows/${workflow.id}/validate`)
    expect(fetch.mock.calls[0][1].method).toBe('POST')
  })

  it.each([
    [404, 'not found'], [409, 'running'], [503, 'storage'], [500, 'could not complete'],
  ])('provides a clear safe HTTP %s error', async (status, text) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'Traceback secret marker' }, status)))
    await expect(deleteWorkflow(workflow.id)).rejects.toMatchObject({ status, message: expect.stringContaining(text) })
    try { await deleteWorkflow(workflow.id) } catch (error) { expect(String(error)).not.toContain('secret marker') }
  })

  it('summarizes structured422 codes instead of exposing raw config or diagnostic content', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: {
      code: 'INVALID_WORKFLOW_STRUCTURE', errors: [
        { code: 'DUPLICATE_NODE_ID', message: 'Traceback private marker' },
        { code: 'INVALID_NODE_REFERENCE', message: 'Private URL marker' },
      ],
    } }, 422)))
    await expect(createWorkflow(payload)).rejects.toMatchObject({ status: 422, message: 'Workflow validation failed: Duplicate node ID; An edge references a missing node.' })
  })

  it('summarizes Pydantic locations without reflecting dynamic keys, rejected input or ctx', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: [
      { type: 'value_error', loc: ['body', 'definition', 'nodes', 0, 'config', 'private-marker'], msg: 'private-marker', input: 'private-marker', ctx: { secret: 'private-marker' } },
    ] }, 422)))
    await expect(updateWorkflow(workflow.id, payload)).rejects.toMatchObject({ status: 422, message: 'Workflow validation failed. Check definition, nodes, config.' })
  })

  it('does not treat inherited object property names as recognized validation codes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: {
      code: 'INVALID_WORKFLOW_STRUCTURE', errors: [{ code: 'constructor', message: 'secret-marker' }],
    } }, 422)))
    await expect(createWorkflow(payload)).rejects.toMatchObject({ message: 'Workflow validation failed. Check node names, connections and configuration; credentials are not allowed.' })
  })

  it('turns network failures into a visible connection error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch internal marker')))
    await expect(listWorkflows()).rejects.toMatchObject({ status: null, message: 'Cannot reach the backend. Check your connection and try again.' })
  })

  it('distinguishes timeout and caller cancellation without waiting for the real timeout', async () => {
    const timeout = new AbortController()
    timeout.abort()
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(timeout.signal)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'TimeoutError')))
    await expect(listWorkflows()).rejects.toThrow('timed out')
    const caller = new AbortController()
    caller.abort()
    await expect(listWorkflows(caller.signal)).rejects.toThrow('cancelled')
  })

  it.each([
    null,
    { ...workflow, id: 'not-a-uuid' },
    { ...workflow, created_at: '2026-10-28T09:00:00' },
    { ...workflow, definition: { schema_version: 2, nodes: [], edges: [] } },
    { ...workflow, definition: { schema_version: 1, nodes: [{ id: 'invalid' }], edges: [] } },
  ])('rejects malformed successful responses before they replace the current graph', async data => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(data)))
    await expect(getWorkflow(workflow.id)).rejects.toMatchObject({ message: expect.stringContaining('current workflow has been kept') })
  })

  it('rejects invalid JSON and duplicate registry entries safely', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('not-json')).mockResolvedValueOnce(response([
      { type: 'same', display_name: 'Same', category: 'utility', description: 'Entry' },
      { type: 'same', display_name: 'Same', category: 'utility', description: 'Entry' },
    ])))
    await expect(listWorkflows()).rejects.toBeInstanceOf(ApiError)
    await expect(getNodeTypes()).rejects.toBeInstanceOf(ApiError)
  })

  it('rejects Python-sized integer configs without suggesting the saved workflow was changed', async () => {
    const large: Workflow = { ...workflow, definition: {
      schema_version: 1,
      nodes: [{ id: 'node', type: 'data.transform', name: 'Transform', position: { x: 0, y: 0 }, config: { identifier: Number.MAX_SAFE_INTEGER + 1 } }], edges: [],
    } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(large)))
    await expect(getWorkflow(workflow.id)).rejects.toMatchObject({ status: 200, message: expect.stringContaining('outside the browser safe integer range') })
  })

  it.each(['9007199254740993', '1' + '0'.repeat(400)])('keeps other workflows discoverable when API-imported config exceeds browser precision (%s), without exposing editable config', async rawInteger => {
    const normal: Workflow = { ...workflow, definition: {
      schema_version: 1,
      nodes: [{ id: 'normal', type: 'custom.future', name: 'Normal', position: { x: 0, y: 0 }, config: { unknown: { value: 'retained' } } }], edges: [],
    } }
    const imported: Workflow = { ...normal, id: 'f3fce261-4bc7-4bd6-9a7c-b33eaaaf10f0', name: 'Imported', definition: {
      schema_version: 1,
      nodes: [
        { id: 'trigger', type: 'trigger.manual', name: 'Trigger', position: { x: 0, y: 0 }, config: {} },
        { id: 'large', type: 'data.transform', name: 'Large', position: { x: 100, y: 0 }, config: { identifier: 'RAW_INTEGER' } },
      ],
      edges: [{ id: 'edge', source: 'trigger', target: 'large', source_handle: 'future', target_handle: null }],
    } }
    // The real JSON decoder rounds a valid Python-sized integer or yields
    // Infinity for larger JSON numbers. Lists must discard those config values;
    // direct editor loads must reject them before replacing the current graph.
    const raw = (value: unknown) => JSON.stringify(value).replace('"RAW_INTEGER"', rawInteger)
    const fetch = vi.fn().mockResolvedValueOnce(new Response(raw([normal, imported])))
      .mockResolvedValueOnce(response(normal)).mockResolvedValueOnce(new Response(raw(imported)))
    vi.stubGlobal('fetch', fetch)
    const items = await listWorkflows()
    expect(items.map(item => item.name)).toEqual(['Draft', 'Imported'])
    expect(items[1].definition.nodes.map(node => node.type)).toEqual(['trigger.manual', 'data.transform'])
    expect(items[1].definition.edges).toEqual(imported.definition.edges)
    expect(items.flatMap(item => item.definition.nodes).every(node => !('config' in node) && !('position' in node))).toBe(true)
    expect(JSON.stringify(items)).not.toContain('identifier')
    await expect(getWorkflow(normal.id)).resolves.toEqual(normal)
    await expect(getWorkflow(imported.id)).rejects.toMatchObject({ name: 'ApiError', status: 200 })
  })

  it.each([
    { ...workflow, id: 'not-a-uuid' },
    { ...workflow, created_at: '2026-10-28T09:00:00' },
    { ...workflow, definition: { schema_version: 2, nodes: [], edges: [] } },
    { ...workflow, definition: { schema_version: 1, nodes: [{ id: 'invalid' }], edges: [] } },
    { ...workflow, definition: { schema_version: 1, nodes: [{ id: 'n', type: 'custom.future', name: 'Node', position: { x: 0, y: 0 }, config: [] }], edges: [] } },
    { ...workflow, definition: { schema_version: 1, nodes: [], edges: [{ id: 'e', source: 'missing', target: 'missing' }] } },
  ])('still rejects malformed workflow list entries rather than weakening structural checks', async item => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([workflow, item])))
    await expect(listWorkflows()).rejects.toBeInstanceOf(ApiError)
  })
})
