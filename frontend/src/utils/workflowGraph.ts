import type { XYPosition } from '@xyflow/react'
import type { FlowEdge, FlowNode, JsonObject, NodeTypeMetadata } from '../types/workflow'

const defaultConfigs: Record<string, () => JsonObject> = {
  'trigger.manual': () => ({}),
  'trigger.schedule': () => ({ cron: '0 9 * * *', timezone: 'UTC' }),
  'action.http_request': () => ({ method: 'GET', url: '', headers: {}, timeout: 10 }),
  'action.webhook': () => ({ url: '', source_node_id: '', headers: {}, timeout: 10 }),
  'logic.condition': () => ({ source_node_id: '', field: '', operator: 'equals', value: null }),
  'data.transform': () => ({ mapping: {} }),
  'utility.logger': () => ({}),
}

export function createFlowNode(metadata: NodeTypeMetadata, position: XYPosition): FlowNode {
  const configFactory = Object.hasOwn(defaultConfigs, metadata.type) ? defaultConfigs[metadata.type] : undefined
  return {
    id: crypto.randomUUID(), type: 'flowpilotNode', position: { ...position },
    data: {
      nodeType: metadata.type, name: metadata.display_name,
      config: configFactory?.() ?? {}, metadata: { ...metadata },
    },
  }
}

function isTrigger(node: FlowNode): boolean {
  return node.data.metadata?.category === 'trigger' || node.data.nodeType.startsWith('trigger.')
}

/** Return a short user-facing reason; null means a new edge is allowed. */
export function validateConnection(
  connection: { source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null },
  nodes: FlowNode[], edges: FlowEdge[],
): string | null {
  const source = nodes.find(node => node.id === connection.source)
  const target = nodes.find(node => node.id === connection.target)
  if (!source || !target) return 'Both ends must reference existing nodes.'
  if (source.id === target.id) return 'A node cannot connect to itself.'
  if (isTrigger(target)) return 'Trigger nodes cannot have incoming connections.'
  const sourceHandle = connection.sourceHandle ?? null
  const targetHandle = connection.targetHandle ?? null
  if (source.data.nodeType === 'logic.condition') {
    if (sourceHandle !== 'true' && sourceHandle !== 'false') return 'Choose the Condition true or false output.'
  } else if (sourceHandle !== null) return 'Only Condition nodes support named output handles.'
  if (targetHandle !== null) return 'Named input handles are not supported.'
  if (edges.some(edge => edge.source === source.id && edge.target === target.id
    && (edge.sourceHandle ?? null) === sourceHandle && (edge.targetHandle ?? null) === targetHandle)) {
    return 'This connection already exists.'
  }
  const outgoing = new Map<string, string[]>()
  for (const edge of edges) outgoing.set(edge.source, [...(outgoing.get(edge.source) ?? []), edge.target])
  const pending = [target.id]
  const visited = new Set<string>()
  while (pending.length) {
    const id = pending.pop()!
    if (id === source.id) return 'This connection would create a cycle.'
    if (visited.has(id)) continue
    visited.add(id)
    pending.push(...(outgoing.get(id) ?? []))
  }
  return null
}

export function getAncestorNodes(nodeId: string, nodes: FlowNode[], edges: FlowEdge[]): FlowNode[] {
  const parents = new Map<string, string[]>()
  for (const edge of edges) parents.set(edge.target, [...(parents.get(edge.target) ?? []), edge.source])
  const ancestors = new Set<string>()
  const pending = [...(parents.get(nodeId) ?? [])]
  while (pending.length) {
    const id = pending.pop()!
    if (id === nodeId || ancestors.has(id)) continue
    ancestors.add(id)
    pending.push(...(parents.get(id) ?? []))
  }
  return nodes.filter(node => ancestors.has(node.id))
}

export function removeNode(nodeId: string, nodes: FlowNode[], edges: FlowEdge[]) {
  return {
    nodes: nodes.filter(node => node.id !== nodeId),
    edges: edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId),
  }
}
