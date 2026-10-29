import { useEffect, useRef, useState } from 'react'
import { executeWorkflow } from '../services/executionApi'
import { ApiError, validateWorkflow } from '../services/workflowApi'
import type { ExecutionResult } from '../types/execution'
import type { FlowNode, ValidationIssue, WorkflowValidationReport } from '../types/workflow'

interface Options {
  workflowId: string | null
  workflowName: string
  nodes: FlowNode[]
  dirty: boolean
  revision: number
  epoch: number
  onComplete: () => void
  onNotice: (notice: { kind: 'error' | 'info'; text: string }) => void
}

export default function useWorkflowExecution(options: Options) {
  const latest = useRef(options)
  latest.current = options
  const [running, setRunning] = useState(false)
  const [validating, setValidating] = useState(false)
  const [execution, setExecution] = useState<ExecutionResult | null>(null)
  const [executionRevision, setExecutionRevision] = useState<number | null>(null)
  const [executionName, setExecutionName] = useState('')
  const [executionNodeNames, setExecutionNodeNames] = useState<Record<string, string>>({})
  const [report, setReport] = useState<WorkflowValidationReport | null>(null)
  const [issues, setIssues] = useState<ValidationIssue[]>([])
  const controller = useRef<AbortController | null>(null)
  const locked = useRef(false)

  useEffect(() => {
    controller.current?.abort()
    locked.current = false
    setRunning(false)
    setValidating(false)
    setExecution(null)
    setExecutionRevision(null)
    setExecutionNodeNames({})
    setReport(null)
    setIssues([])
    return () => controller.current?.abort()
  }, [options.workflowId, options.epoch])

  useEffect(() => { setReport(null); setIssues([]) }, [options.revision])

  const perform = async (execute: boolean) => {
    if (locked.current) return
    const snapshot = latest.current
    const notice = snapshot.onNotice
    if (!snapshot.workflowId || snapshot.dirty) {
      notice({ kind: 'info', text: execute
        ? 'You have unsaved changes. Save your workflow before running.'
        : 'Save your changes before validating the saved workflow.' })
      return
    }
    if (execute) {
      if (snapshot.nodes.some(node => node.data.nodeType === 'trigger.schedule')) {
        notice({ kind: 'info', text: 'This workflow runs on a schedule.' })
        return
      }
      if (snapshot.nodes.filter(node => node.data.nodeType === 'trigger.manual').length !== 1) {
        notice({ kind: 'error', text: 'A manual run requires exactly one Manual Trigger. Drafts can still be saved.' })
        return
      }
    }
    const request = new AbortController()
    controller.current = request
    locked.current = true
    setValidating(true)
    setIssues([])
    if (execute) { setExecution(null); setExecutionRevision(null) }
    let submitted = false
    const active = () => !request.signal.aborted && latest.current.epoch === snapshot.epoch
      && latest.current.workflowId === snapshot.workflowId
    try {
      const checked = await validateWorkflow(snapshot.workflowId, request.signal)
      if (!active()) return
      if (latest.current.revision !== snapshot.revision || latest.current.dirty) {
        notice({ kind: 'info', text: 'Workflow changed during validation. Save your changes before running.' })
        return
      }
      setReport(checked)
      setValidating(false)
      const valid = checked.can_save && checked.structural.valid && checked.execution_readiness.valid
      if (!execute) {
        notice({ kind: valid ? 'info' : 'error', text: valid
          ? 'Saved graph is valid. This checks graph structure; executor configuration is checked when executing.'
          : 'Workflow validation failed. Review the errors in Validation.' })
        return
      }
      if (!valid) {
        notice({ kind: 'error', text: 'Workflow validation failed. Review the errors in Validation.' })
        return
      }
      // The execute endpoint performs strict executor/config readiness. Unlike
      // ordinary requests it deliberately has no short frontend timeout.
      submitted = true
      setRunning(true)
      const result = await executeWorkflow(snapshot.workflowId, request.signal)
      if (!active()) return
      if (result.workflow_id !== snapshot.workflowId) throw new Error('Execution returned a different workflow. Check history for the actual outcome.')
      setExecution(result)
      setExecutionRevision(snapshot.revision)
      setExecutionName(snapshot.workflowName)
      setExecutionNodeNames(Object.fromEntries(snapshot.nodes.map((node) => [node.id, node.data.name])))
      latest.current.onComplete()
    } catch (error) {
      if (!active()) return
      if (error instanceof ApiError && error.issues) setIssues(error.issues)
      const unknown = !(error instanceof ApiError) || error.status === null || error.status === 503 || error.status >= 500
      const text = error instanceof Error ? error.message : 'The request could not be completed.'
      notice({ kind: 'error', text: execute && submitted && unknown
        ? `Execution outcome is unknown. ${text} Check execution history before trying again; the backend may continue.` : text })
    } finally {
      if (active()) {
        locked.current = false
        setRunning(false)
        setValidating(false)
      }
    }
  }
  return {
    running, validating, execution, executionName, executionNodeNames, report, issues,
    stale: execution !== null && (executionRevision !== options.revision || options.dirty),
    run: () => perform(true), validate: () => perform(false),
  }
}
