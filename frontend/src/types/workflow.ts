import type { Edge, Node, XYPosition } from '@xyflow/react'

export type JsonValue = string | number | boolean | null | JsonValue[] | JsonObject
export type JsonObject = { [key: string]: JsonValue }

export interface BackendNode {
  id: string
  type: string
  name: string
  position: XYPosition
  config: JsonObject
}

export interface BackendEdge {
  id: string
  source: string
  target: string
  source_handle?: string | null
  target_handle?: string | null
}

export interface WorkflowDefinition {
  schema_version: 1
  nodes: BackendNode[]
  edges: BackendEdge[]
}

export interface WorkflowPayload {
  name: string
  description: string | null
  definition: WorkflowDefinition
}

export interface Workflow extends WorkflowPayload {
  id: string
  created_at: string
  updated_at: string
}

export interface NodeTypeMetadata {
  type: string
  display_name: string
  category: string
  description: string
}

export interface FlowNodeData extends Record<string, unknown> {
  nodeType: string
  name: string
  config: JsonObject
  metadata?: NodeTypeMetadata
  executionStatus?: string
  executionId?: string
}

export type FlowNode = Node<FlowNodeData, 'flowpilotNode'>
export type FlowEdge = Edge

export interface ValidationIssue {
  code: string
  message: string
  node_id?: string | null
  edge_id?: string | null
}

export interface ValidationResult {
  valid: boolean
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
}

export interface WorkflowValidationReport {
  can_save: boolean
  structural: ValidationResult
  execution_readiness: ValidationResult
}
