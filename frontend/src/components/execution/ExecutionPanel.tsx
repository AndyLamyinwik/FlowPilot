import { useState } from 'react'
import type { ExecutionDetail, ExecutionResult, NodeExecutionResult } from '../../types/execution'
import { formatDuration, formatTimestamp, safeExecutionError, sanitizeOutput } from '../../utils/executionDisplay'
import ExecutionStatus from './ExecutionStatus'

export interface ExecutionPanelProps {
  execution: ExecutionResult | ExecutionDetail | null
  workflowName: string
  triggerType?: 'manual' | 'schedule'
  selectedNodeId?: string | null
  nodeNames?: Record<string, string>
  historical?: boolean
  onSelectNode?: (id: string) => void
}

function duration(item: { started_at?: string | null; finished_at?: string | null; duration_ms?: number | null }) {
  if (item.duration_ms != null) return item.duration_ms
  if (!item.started_at || !item.finished_at) return null
  const milliseconds = Date.parse(item.finished_at) - Date.parse(item.started_at)
  return Number.isFinite(milliseconds) ? Math.max(0, milliseconds) : null
}

function NodeDetail({ node, name }: { node: NodeExecutionResult; name?: string }) {
  return (
    <section className="execution-node-detail" aria-label="Node execution details">
      <h3>{name || node.node_id}</h3>
      <dl className="execution-metadata">
        <div><dt>Node ID</dt><dd><code>{node.node_id}</code></dd></div>
        {name && <div><dt>Node name</dt><dd>{name}</dd></div>}
        <div><dt>Status</dt><dd><ExecutionStatus status={node.status} /></dd></div>
        <div><dt>Started (UTC)</dt><dd>{formatTimestamp(node.started_at)}</dd></div>
        <div><dt>Finished (UTC)</dt><dd>{formatTimestamp(node.finished_at)}</dd></div>
        <div><dt>Duration</dt><dd>{formatDuration(duration(node))}</dd></div>
      </dl>
      {node.error && <p className="execution-error" role="alert">{safeExecutionError(node.error)}</p>}
      <h4>Output</h4>
      {node.output == null
        ? <p className="muted">Output not stored or unavailable.</p>
        : <pre className="execution-json" tabIndex={0} aria-label="Node output">{JSON.stringify(sanitizeOutput(node.output), null, 2)}</pre>}
      {node.output != null && <p className="field-help">Common sensitive fields are redacted and large output is limited. Text may still contain sensitive information.</p>}
    </section>
  )
}

function Result({ execution, workflowName, triggerType, selectedNodeId, nodeNames = {}, historical = false, onSelectNode }: Omit<ExecutionPanelProps, 'execution'> & { execution: ExecutionResult | ExecutionDetail }) {
  const [localNodeId, setLocalNodeId] = useState<string | null>(null)
  const selected = execution.node_results.find(node => node.node_id === (selectedNodeId ?? localNodeId))
    ?? execution.node_results[0]
  const trigger = execution.trigger_type ?? triggerType ?? 'manual'
  const counts = execution.node_results.reduce<Record<string, number>>((result, node) => {
    const key = node.status
    result[key] = (Object.hasOwn(result, key) ? result[key] : 0) + 1
    return result
  }, Object.create(null) as Record<string, number>)

  return (
    <section className="execution-panel" aria-label={historical ? 'Historical execution details' : 'Execution result'}>
      <div className="execution-panel-heading"><h2>{historical ? 'Execution Detail' : 'Execution Result'}</h2><ExecutionStatus status={execution.status} /></div>
      {historical && <p className="execution-notice">Historical result. This execution may use a different workflow version. Canvas status is unchanged.</p>}
      <dl className="execution-metadata">
        <div><dt>Execution ID</dt><dd><code>{execution.execution_id}</code></dd></div>
        <div><dt>Workflow</dt><dd>{workflowName}</dd></div>
        <div><dt>Workflow ID</dt><dd><code>{execution.workflow_id}</code></dd></div>
        <div><dt>Trigger</dt><dd>{trigger === 'schedule' ? 'Schedule' : 'Manual'}</dd></div>
        <div><dt>Started (UTC)</dt><dd>{formatTimestamp(execution.started_at)}</dd></div>
        <div><dt>Finished (UTC)</dt><dd>{formatTimestamp(execution.finished_at)}</dd></div>
        <div><dt>Duration</dt><dd>{formatDuration(duration(execution))}</dd></div>
      </dl>
      <p className="execution-counts">Nodes: {execution.node_results.length} · Success: {counts.success ?? 0} · Failed: {counts.failed ?? 0} · Skipped: {counts.skipped ?? 0}</p>
      {execution.error && <p className="execution-error" role="alert">{safeExecutionError(execution.error)}</p>}
      {'history_truncated' in execution && execution.history_truncated && <p className="execution-notice">This history record was limited in size. Some outputs or node summaries were not stored.</p>}
      {execution.node_results.length === 0 ? <p className="muted">No node results available.</p> : <>
        <div className="execution-node-list" aria-label="Execution nodes">
          {execution.node_results.map(node => <button type="button" key={node.node_id} aria-pressed={selected?.node_id === node.node_id}
            className="execution-node-button" onClick={() => { setLocalNodeId(node.node_id); if (!historical) onSelectNode?.(node.node_id) }}>
            <span>{!historical && nodeNames[node.node_id] ? nodeNames[node.node_id] : node.node_id}</span><ExecutionStatus status={node.status} />
          </button>)}
        </div>
        {selected && <NodeDetail node={selected} name={!historical ? nodeNames[selected.node_id] : undefined} />}
      </>}
    </section>
  )
}

export default function ExecutionPanel(props: ExecutionPanelProps) {
  return props.execution
    ? <Result key={props.execution.execution_id} {...props} execution={props.execution} />
    : <section className="execution-panel" aria-label="Execution result"><h2>Execution Result</h2><p className="muted">Run a saved manual workflow to see its result.</p></section>
}
