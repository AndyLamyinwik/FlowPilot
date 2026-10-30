import type {
  BackendEdge, BackendNode, FlowEdge, FlowNode, JsonObject,
  NodeTypeMetadata, WorkflowDefinition,
} from '../types/workflow'

const secretKeys = new Set([
  'password', 'passwd', 'pwd', 'apikey', 'xapikey', 'secret', 'clientsecret',
  'accesstoken', 'refreshtoken', 'authtoken', 'xauthtoken', 'bearertoken',
  'authorization', 'cookie', 'setcookie', 'proxyauthorization', 'privatekey',
])

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function nonblank(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function label(key: string): string {
  return key.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '')
}

/** Validate data without imposing execution readiness on an unfinished Draft. */
export function validateJsonObject(value: unknown, checkSecrets = true): asserts value is JsonObject {
  if (!object(value)) throw new Error('Node config must be a JSON object.')
  const active = new Set<object>()
  function visit(item: unknown): void {
    if (item === null || typeof item === 'string' || typeof item === 'boolean') return
    if (typeof item === 'number' && Number.isFinite(item)) {
      if (Number.isInteger(item) && !Number.isSafeInteger(item)) {
        throw new Error('Config integers exceed the browser safe range. Use strings for large identifiers; this workflow has not been changed.')
      }
      return
    }
    if (typeof item !== 'object' || item === null) throw new Error('Config must contain finite JSON values.')
    if (active.has(item)) throw new Error('Config must not contain circular references.')
    if (!Array.isArray(item) && Object.getPrototypeOf(item) !== Object.prototype && Object.getPrototypeOf(item) !== null) {
      throw new Error('Config must contain only JSON objects and values.')
    }
    if (Object.getOwnPropertySymbols(item).length) throw new Error('Config keys must be JSON strings.')
    active.add(item)
    if (Array.isArray(item)) {
      for (const child of item) visit(child)
    } else {
      for (const [key, child] of Object.entries(item)) {
        if (checkSecrets && secretKeys.has(label(key)) && child !== null && child !== '') {
          throw new Error('Plaintext credentials are not allowed in node config.')
        }
        visit(child)
      }
    }
    active.delete(item)
  }
  try {
    visit(value)
  } catch (error) {
    if (error instanceof RangeError) throw new Error('Config nesting is too deep.')
    throw error
  }
}

function validateCredentialHeaders(node: BackendNode): void {
  if (!['action.http_request', 'action.webhook'].includes(node.type)) return
  if (!object(node.config.headers)) return
  if (Object.keys(node.config.headers).some(key => secretKeys.has(label(key)))) {
    throw new Error('Authorization, Cookie and other credential headers cannot be saved.')
  }
}

/** Runtime-check API data before replacing the current graph. Unknown config is retained. */
export function assertWorkflowDefinition(value: unknown, validateConfigValues = true): asserts value is WorkflowDefinition {
  if (!object(value) || value.schema_version !== 1 || !Array.isArray(value.nodes) || !Array.isArray(value.edges)) {
    throw new Error('Invalid workflow definition or unsupported schema version.')
  }
  const nodeIds = new Set<string>()
  for (const node of value.nodes) {
    if (!object(node) || !nonblank(node.id) || !nonblank(node.type) || !nonblank(node.name)
      || !object(node.position) || typeof node.position.x !== 'number' || typeof node.position.y !== 'number'
      || !Number.isFinite(node.position.x) || !Number.isFinite(node.position.y)) {
      throw new Error('Invalid node data or position.')
    }
    if (nodeIds.has(node.id)) throw new Error('Duplicate node ID in workflow.')
    if (node.id !== node.id.trim() || node.type !== node.type.trim()) throw new Error('Node IDs and types cannot contain surrounding spaces.')
    nodeIds.add(node.id)
    if (validateConfigValues) validateJsonObject(node.config, false)
    else if (!object(node.config)) throw new Error('Node config must be a JSON object.')
  }
  const edgeIds = new Set<string>()
  for (const edge of value.edges) {
    if (!object(edge) || !nonblank(edge.id) || !nonblank(edge.source) || !nonblank(edge.target)
      || !nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      throw new Error('Invalid edge or missing node reference.')
    }
    if (edgeIds.has(edge.id)) throw new Error('Duplicate edge ID in workflow.')
    if (edge.id !== edge.id.trim() || edge.source !== edge.source.trim() || edge.target !== edge.target.trim()) {
      throw new Error('Edge IDs and references cannot contain surrounding spaces.')
    }
    if (edge.source === edge.target) throw new Error('A node cannot connect to itself.')
    edgeIds.add(edge.id)
    for (const handle of [edge.source_handle, edge.target_handle]) {
      if (handle !== undefined && handle !== null && !nonblank(handle)) throw new Error('Invalid edge handle.')
    }
  }
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function toReactFlow(definition: WorkflowDefinition, metadata: NodeTypeMetadata[] = []) {
  assertWorkflowDefinition(definition)
  const byType = new Map(metadata.map(item => [item.type, item]))
  return {
    schemaVersion: definition.schema_version,
    nodes: definition.nodes.map((node): FlowNode => ({
      id: node.id,
      type: 'flowpilotNode',
      position: { ...node.position },
      data: {
        nodeType: node.type, name: node.name, config: clone(node.config),
        ...(byType.has(node.type) ? { metadata: { ...byType.get(node.type)! } } : {}),
      },
    })),
    edges: definition.edges.map((edge): FlowEdge => ({
      id: edge.id, source: edge.source, target: edge.target,
      sourceHandle: edge.source_handle ?? null, targetHandle: edge.target_handle ?? null,
    })),
  }
}

export function toWorkflowDefinition(
  nodes: FlowNode[], edges: FlowEdge[], schemaVersion: number = 1,
): WorkflowDefinition {
  if (schemaVersion !== 1) throw new Error('Unsupported workflow schema version.')
  const definition: WorkflowDefinition = {
    schema_version: schemaVersion,
    nodes: nodes.map((node): BackendNode => ({
      id: node.id, type: node.data.nodeType, name: node.data.name,
      position: { x: node.position.x, y: node.position.y }, config: node.data.config,
    })),
    edges: edges.map((edge): BackendEdge => ({
      id: edge.id, source: edge.source, target: edge.target,
      source_handle: edge.sourceHandle ?? null, target_handle: edge.targetHandle ?? null,
    })),
  }
  assertWorkflowDefinition(definition)
  for (const node of definition.nodes) {
    validateJsonObject(node.config)
    validateCredentialHeaders(node)
  }
  return clone(definition)
}
