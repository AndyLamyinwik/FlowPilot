import { describe, expect, it } from 'vitest'
import type { Connection } from '@xyflow/react'
import type { FlowEdge, FlowNode, NodeTypeMetadata } from '../types/workflow'
import { createFlowNode, getAncestorNodes, removeNode, validateConnection } from './workflowGraph'

const metadata = (type: string): NodeTypeMetadata => ({ type, display_name: type, category: type.split('.')[0], description: 'Example node' })
function node(id: string, type = 'utility.logger'): FlowNode {
  return { ...createFlowNode(metadata(type), { x: 0, y: 0 }), id }
}
function connect(source: string, target: string, sourceHandle: string | null = null, targetHandle: string | null = null): Connection {
  return { source, target, sourceHandle, targetHandle }
}
function edge(id: string, source: string, target: string, sourceHandle: string | null = null): FlowEdge {
  return { id, source, target, sourceHandle, targetHandle: null }
}

describe('workflow graph operations', () => {
  it('creates collision-free nodes with independent config and exact supplied canvas positions', () => {
    const first = createFlowNode(metadata('trigger.schedule'), { x: 45.25, y: -100 })
    const second = createFlowNode(metadata('trigger.schedule'), { x: 45.25, y: -100 })
    expect(first.id).not.toBe(second.id)
    expect(first.position).toEqual({ x: 45.25, y: -100 })
    expect(first.data.config).toEqual({ cron: '0 9 * * *', timezone: 'UTC' })
    first.data.config.timezone = 'Asia/Tokyo'
    expect(second.data.config.timezone).toBe('UTC')
  })

  it('uses safe incomplete HTTP defaults and preserves backend metadata for future types', () => {
    expect(createFlowNode(metadata('action.http_request'), { x: 0, y: 0 }).data.config).toEqual({ method: 'GET', url: '', headers: {}, timeout: 10 })
    expect(createFlowNode(metadata('custom.future'), { x: 0, y: 0 }).data).toMatchObject({ nodeType: 'custom.future', config: {}, metadata: metadata('custom.future') })
  })

  it.each(['__proto__', 'constructor', 'toString'])('does not invoke inherited object properties for future type %s', type => {
    expect(createFlowNode(metadata(type), { x: 0, y: 0 }).data.config).toEqual({})
  })

  it('accepts ordinary DAG edges and both Condition branches to the same target', () => {
    const nodes = [node('manual', 'trigger.manual'), node('condition', 'logic.condition'), node('logger')]
    expect(validateConnection(connect('manual', 'condition'), nodes, [])).toBeNull()
    const existing = [edge('true', 'condition', 'logger', 'true')]
    expect(validateConnection(connect('condition', 'logger', 'false'), nodes, existing)).toBeNull()
    expect(validateConnection(connect('condition', 'logger', 'true'), nodes, [])).toBeNull()
  })

  it.each([
    ['self connection', connect('a', 'a')],
    ['missing source', connect('missing', 'a')],
    ['missing target', connect('a', 'missing')],
    ['trigger target', connect('a', 'manual')],
    ['named noncondition output', connect('a', 'b', 'true')],
    ['named input', connect('a', 'b', null, 'input')],
    ['missing condition handle', connect('condition', 'a')],
    ['invalid condition handle', connect('condition', 'a', 'other')],
  ])('rejects %s', (_, connection) => {
    const nodes = [node('a'), node('b'), node('manual', 'trigger.manual'), node('condition', 'logic.condition')]
    expect(validateConnection(connection, nodes, [])).toBeTypeOf('string')
  })

  it('rejects duplicate ordinary and condition edges with matching handles', () => {
    const nodes = [node('a'), node('b'), node('condition', 'logic.condition')]
    expect(validateConnection(connect('a', 'b'), nodes, [edge('existing', 'a', 'b')])).toContain('already exists')
    expect(validateConnection(connect('condition', 'b', 'false'), nodes, [edge('existing', 'condition', 'b', 'false')])).toContain('already exists')
  })

  it('rejects cycles through several nodes without recursing indefinitely on an existing Draft cycle', () => {
    const nodes = [node('a'), node('b'), node('c'), node('d')]
    const edges = [edge('a-b', 'a', 'b'), edge('b-c', 'b', 'c')]
    expect(validateConnection(connect('c', 'a'), nodes, edges)).toContain('cycle')
    const draft = [...edges, edge('c-a', 'c', 'a')]
    expect(validateConnection(connect('d', 'a'), nodes, draft)).toBeNull()
  })

  it('uses Registry trigger category for future trigger types', () => {
    const future = node('future', 'custom.trigger')
    future.data.metadata!.category = 'trigger'
    expect(validateConnection(connect('logger', 'future'), [node('logger'), future], [])).toContain('Trigger')
  })

  it('removes only the deleted node and its incident edges', () => {
    const nodes = [node('a'), node('b'), node('c')]
    const edges = [edge('a-b', 'a', 'b'), edge('b-c', 'b', 'c'), edge('a-c', 'a', 'c')]
    const result = removeNode('b', nodes, edges)
    expect(result.nodes.map(item => item.id)).toEqual(['a', 'c'])
    expect(result.edges.map(item => item.id)).toEqual(['a-c'])
    expect(nodes).toHaveLength(3)
    expect(edges).toHaveLength(3)
  })

  it('offers only local graph ancestors in original node order, even on a Draft cycle', () => {
    const nodes = [node('unrelated'), node('direct'), node('ancestor'), node('selected')]
    const edges = [edge('a-d', 'ancestor', 'direct'), edge('d-s', 'direct', 'selected'), edge('s-d', 'selected', 'direct')]
    expect(getAncestorNodes('selected', nodes, edges).map(item => item.id)).toEqual(['direct', 'ancestor'])
    expect(getAncestorNodes('unrelated', nodes, edges)).toEqual([])
  })
})
