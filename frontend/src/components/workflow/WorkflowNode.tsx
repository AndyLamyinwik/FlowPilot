import { memo, type CSSProperties } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { FlowNode } from '../../types/workflow'
import NodeIcon from './NodeIcon'
import { CATEGORY_PRESENTATION, nodeCategory } from './nodePresentation'
import ExecutionStatus, { statusPresentation } from '../execution/ExecutionStatus'

function WorkflowNode({ id, data, selected, isConnectable }: NodeProps<FlowNode>) {
  const category = nodeCategory(data.nodeType, data.metadata)
  const trigger = category === 'trigger' || data.nodeType.startsWith('trigger.')
  const condition = data.nodeType === 'logic.condition'
  const presentation = CATEGORY_PRESENTATION[category]
  const executionStatus = typeof data.executionStatus === 'string' ? data.executionStatus : null
  const executionClass = executionStatus ? ` execution-node-${statusPresentation(executionStatus).className}` : ''
  return (
    <div className={`workflow-node category-${category}${selected ? ' selected' : ''}${executionClass}`}
      style={{ '--node-accent': presentation.color } as CSSProperties} data-node-id={id}
      data-execution-id={typeof data.executionId === 'string' ? data.executionId : undefined}>
      {!trigger && <Handle type="target" position={Position.Left} isConnectable={isConnectable} aria-label={`${data.name} input`} />}
      <div className="workflow-node-heading">
        <span className="workflow-node-icon"><NodeIcon type={data.nodeType} /></span>
        <div className="workflow-node-title"><strong title={data.name}>{data.name}</strong><span>{presentation.label}</span></div>
      </div>
      <code className="workflow-node-type">{data.nodeType}</code>
      <p className="workflow-node-description">{data.metadata?.description ?? 'Configuration is preserved. This node may need a newer editor.'}</p>
      {executionStatus && <div className="workflow-node-execution"><ExecutionStatus status={executionStatus} /></div>}
      {condition ? (
        <div className="condition-outputs">
          <span className="condition-output condition-true">True</span>
          <span className="condition-output condition-false">False</span>
          <Handle id="true" type="source" position={Position.Right} className="condition-handle-true"
            style={{ top: 'calc(100% - 46px)' }} isConnectable={isConnectable} aria-label={`${data.name} true output`} />
          <Handle id="false" type="source" position={Position.Right} className="condition-handle-false"
            style={{ top: 'calc(100% - 20px)' }} isConnectable={isConnectable} aria-label={`${data.name} false output`} />
        </div>
      ) : <Handle type="source" position={Position.Right} isConnectable={isConnectable} aria-label={`${data.name} output`} />}
    </div>
  )
}

export default memo(WorkflowNode)
