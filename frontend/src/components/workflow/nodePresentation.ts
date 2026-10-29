import type { NodeTypeMetadata } from '../../types/workflow'

export type NodeCategory = 'trigger' | 'action' | 'logic' | 'data' | 'utility' | 'unknown'

export const CATEGORY_PRESENTATION: Record<NodeCategory, { label: string; color: string }> = {
  trigger: { label: 'Triggers', color: '#55d99b' },
  action: { label: 'Actions', color: '#70acff' },
  logic: { label: 'Logic', color: '#ba96ff' },
  data: { label: 'Data', color: '#f7b46d' },
  utility: { label: 'Utility', color: '#a6b2c3' },
  unknown: { label: 'Other', color: '#a6b2c3' },
}

export function nodeCategory(nodeType: string, metadata?: NodeTypeMetadata): NodeCategory {
  const category = metadata?.category ?? nodeType.split('.')[0]
  return category === 'trigger' || category === 'action' || category === 'logic'
    || category === 'data' || category === 'utility' ? category : 'unknown'
}

export const FLOWPILOT_NODE_MIME = 'application/flowpilot-node-type'
