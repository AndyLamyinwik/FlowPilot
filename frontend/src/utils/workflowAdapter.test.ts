import { describe, expect, it } from 'vitest'
import type { NodeTypeMetadata, WorkflowDefinition } from '../types/workflow'
import { assertWorkflowDefinition, toReactFlow, toWorkflowDefinition, validateJsonObject } from './workflowAdapter'

const metadata: NodeTypeMetadata[] = [{
  type: 'logic.condition', display_name: 'Condition', category: 'logic', description: 'Choose a branch',
}]

function definition(): WorkflowDefinition {
  return {
    schema_version: 1,
    nodes: [
      { id: 'condition', type: 'logic.condition', name: 'Has title', position: { x: -250.5, y: 140.25 }, config: { source_node_id: 'source', field: 'body.title', operator: 'exists', custom: [null, false, 0, { nested: 'value' }] } },
      { id: 'future', type: 'custom.future', name: 'Future node', position: { x: 550, y: -0.25 }, config: { unknown: { preserve: ['all', 'fields'] } } },
    ],
    edges: [
      { id: 'edge-true', source: 'condition', target: 'future', source_handle: 'true', target_handle: null },
      { id: 'edge-false', source: 'condition', target: 'future', source_handle: 'false', target_handle: 'future-port' },
    ],
  }
}

describe('workflow adapter', () => {
  it('round trips every backend field, condition handles and unknown config without persisting UI state', () => {
    const backend = definition()
    const graph = toReactFlow(backend, metadata)
    expect(graph.nodes[0]).toMatchObject({ type: 'flowpilotNode', data: { nodeType: 'logic.condition', name: 'Has title', metadata: metadata[0] } })
    expect(graph.nodes[1].data.nodeType).toBe('custom.future')
    expect(graph.nodes[1].data.metadata).toBeUndefined()
    graph.nodes[0].selected = true
    graph.nodes[0].measured = { width: 280, height: 100 }
    graph.nodes[0].data.temporaryUI = { expanded: true }
    graph.edges[0].selected = true
    graph.edges[0].style = { stroke: 'purple' }
    expect(toWorkflowDefinition(graph.nodes, graph.edges, graph.schemaVersion)).toEqual(backend)
  })

  it('detaches input config and both conversion results', () => {
    const backend = definition()
    const graph = toReactFlow(backend)
    graph.nodes[0].data.config.field = 'changed'
    expect(backend.nodes[0].config.field).toBe('body.title')
    const saved = toWorkflowDefinition(graph.nodes, graph.edges)
    saved.nodes[0].config.field = 'mutated saved copy'
    expect(graph.nodes[0].data.config.field).toBe('changed')
    graph.nodes[0].position.x = 1000
    expect(backend.nodes[0].position.x).toBe(-250.5)
  })

  it('accepts empty and unfinished Drafts without an execution readiness check', () => {
    const empty: WorkflowDefinition = { schema_version: 1, nodes: [], edges: [] }
    const emptyGraph = toReactFlow(empty)
    expect(toWorkflowDefinition(emptyGraph.nodes, emptyGraph.edges)).toEqual(empty)
    const draft = definition()
    draft.nodes[0].config = { url: '' }
    draft.nodes[0].name = 'Incomplete but saveable'
    const graph = toReactFlow(draft)
    expect(toWorkflowDefinition(graph.nodes, graph.edges)).toEqual(draft)
  })

  it('keeps a pre-existing multi-node cycle saveable as a Draft', () => {
    const backend = definition()
    backend.edges = [
      { id: 'a', source: 'condition', target: 'future', source_handle: 'true', target_handle: null },
      { id: 'b', source: 'future', target: 'condition', source_handle: null, target_handle: null },
    ]
    const graph = toReactFlow(backend)
    expect(toWorkflowDefinition(graph.nodes, graph.edges)).toEqual(backend)
  })

  it('normalizes omitted optional handles to null', () => {
    const backend = definition()
    backend.edges = [{ id: 'a', source: 'condition', target: 'future' }]
    const graph = toReactFlow(backend)
    expect(graph.edges[0].sourceHandle).toBeNull()
    expect(toWorkflowDefinition(graph.nodes, graph.edges).edges[0]).toEqual({ ...backend.edges[0], source_handle: null, target_handle: null })
  })

  it.each([
    ['duplicate nodes', (data: WorkflowDefinition) => data.nodes.push(data.nodes[0])],
    ['duplicate edges', (data: WorkflowDefinition) => data.edges.push(data.edges[0])],
    ['dangling edges', (data: WorkflowDefinition) => { data.edges[0].target = 'missing' }],
    ['nonfinite positions', (data: WorkflowDefinition) => { data.nodes[0].position.x = NaN }],
    ['empty name', (data: WorkflowDefinition) => { data.nodes[0].name = ' ' }],
    ['surrounding ID spaces', (data: WorkflowDefinition) => { data.nodes[0].id = ' condition ' }],
    ['self loops', (data: WorkflowDefinition) => { data.edges[0].target = 'condition' }],
  ])('rejects structurally invalid data: %s', (_, mutate) => {
    const data = definition()
    mutate(data)
    expect(() => assertWorkflowDefinition(data)).toThrow()
  })

  it('rejects unsupported schema versions instead of silently rewriting them', () => {
    expect(() => toReactFlow({ ...definition(), schema_version: 2 } as never)).toThrow('schema')
    const graph = toReactFlow(definition())
    expect(() => toWorkflowDefinition(graph.nodes, graph.edges, 2)).toThrow('schema')
  })

  it.each(['Authorization', 'Cookie', 'Proxy-Authorization', 'X-API-Key'])('blocks saving credential header %s even when empty', name => {
    const backend = definition()
    backend.nodes[0].type = 'action.http_request'
    backend.nodes[0].config = { headers: { [name]: '' } }
    const graph = toReactFlow(backend)
    expect(() => toWorkflowDefinition(graph.nodes, graph.edges)).toThrow('credential headers')
  })

  it('blocks nested plaintext credentials while retaining safe empty Draft fields', () => {
    expect(() => validateJsonObject({ nested: [{ api_key: 'secret marker' }] })).toThrow('credentials')
    expect(() => validateJsonObject({ password: '', api_key: null, credential_ref: 'future-reference' })).not.toThrow()
  })

  it.each([NaN, Infinity, undefined, 2n, new Date(), { [Symbol('hidden')]: 2 }])('rejects non-JSON data', value => {
    expect(() => validateJsonObject({ value })).toThrow()
  })

  it('rejects circular config without mutating it', () => {
    const config: Record<string, unknown> = {}
    config.nested = config
    expect(() => validateJsonObject(config)).toThrow('circular')
    expect(config.nested).toBe(config)
  })

  it('rejects unsafe integers on load and save instead of silently rounding backend config', () => {
    const backend = definition()
    // JSON.parse already rounds this Python-sized integer; the range check must
    // still fail closed before the graph can be edited and written back.
    backend.nodes[1].config = JSON.parse('{"identifier":9007199254740993}')
    expect(() => toReactFlow(backend)).toThrow('safe range')
    const graph = toReactFlow(definition())
    graph.nodes[1].data.config.identifier = Number.MAX_SAFE_INTEGER + 1
    expect(() => toWorkflowDefinition(graph.nodes, graph.edges)).toThrow('safe range')
    expect(() => validateJsonObject({ low: Number.MIN_SAFE_INTEGER, high: Number.MAX_SAFE_INTEGER, fraction: 0.125 })).not.toThrow()
  })

  it('retains special JSON keys without assigning them to object prototypes', () => {
    const backend = definition()
    backend.nodes[1].config = JSON.parse('{"__proto__":{"key":"retained"},"constructor":"retained"}')
    const graph = toReactFlow(backend)
    expect(toWorkflowDefinition(graph.nodes, graph.edges)).toEqual(backend)
    expect(({} as Record<string, unknown>).key).toBeUndefined()
  })
})
