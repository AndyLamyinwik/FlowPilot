import type { ValidationIssue, WorkflowValidationReport } from '../../types/workflow'
import { safeValidationIssueMessage } from '../../utils/executionDisplay'

export interface ValidationPanelProps {
  report: WorkflowValidationReport | null
  issues?: ValidationIssue[]
  onSelectNode: (id: string) => void
}

function unique(items: ValidationIssue[]) {
  const seen = new Set<string>()
  return items.filter(item => {
    const key = JSON.stringify([item.code, item.node_id, item.edge_id])
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export default function ValidationPanel({ report, issues = [], onSelectNode }: ValidationPanelProps) {
  const errors = unique([...(report?.structural.errors ?? []), ...(report?.execution_readiness.errors ?? []), ...issues])
  const warnings = unique([...(report?.structural.warnings ?? []), ...(report?.execution_readiness.warnings ?? [])])
  const checked = report !== null || issues.length > 0
  const passed = checked && errors.length === 0 && report?.structural.valid && report.execution_readiness.valid
  const list = (items: ValidationIssue[], warning = false) => <ul className={`validation-issues${warning ? ' validation-warnings' : ''}`}>
    {items.map((item, index) => <li key={`${item.code}-${item.node_id ?? ''}-${index}`}>
      <span aria-hidden="true">{warning ? '⚠' : '✕'}</span><span>{safeValidationIssueMessage(item)}</span>
      {item.node_id && <button className="secondary-button" type="button" onClick={() => onSelectNode(item.node_id!)}>Locate node {item.node_id}</button>}
    </li>)}
  </ul>

  return <section className="validation-panel" aria-label="Workflow validation">
    <div className="execution-panel-heading"><h2>Workflow Validation</h2>{checked && <span className={passed ? 'validation-passed' : 'validation-failed'}>{passed ? 'Validation Passed' : 'Validation Failed'}</span>}</div>
    {!checked && <p className="muted">Validate a saved workflow to check its graph structure.</p>}
    <p className="field-help">Save Draft, Validate and Run are separate actions. Graph validation does not verify every executor configuration; the Execute API performs the final readiness check.</p>
    {errors.length > 0 && <div><h3>Errors</h3>{list(errors)}</div>}
    {warnings.length > 0 && <div><h3>Warnings</h3>{list(warnings, true)}</div>}
    {checked && errors.length === 0 && warnings.length === 0 && <p className="muted">{passed ? 'No graph validation issues.' : 'The saved graph is not ready for execution.'}</p>}
  </section>
}
