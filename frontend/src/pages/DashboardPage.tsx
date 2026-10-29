import { useEffect, useRef, useState } from 'react'
import BackendStatus from '../components/BackendStatus'
import Modal from '../components/ui/Modal'
import { deleteWorkflow, listWorkflows } from '../services/workflowApi'
import type { Workflow } from '../types/workflow'

function triggerLabel(workflow: Workflow): string {
  const triggers = workflow.definition.nodes.filter((node) => node.type.startsWith('trigger.'))
  if (triggers.length !== 1) return triggers.length ? 'Multiple triggers · Draft' : 'No trigger · Draft'
  if (triggers[0].type === 'trigger.manual') return 'Manual'
  if (triggers[0].type === 'trigger.schedule') return 'Schedule'
  return 'Other trigger'
}

function updatedAt(value: string): string {
  const date = new Date(value)
  return Number.isFinite(date.getTime()) ? `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC` : 'Unavailable'
}

const errorMessage = (failure: unknown) => failure instanceof Error ? failure.message : 'Request failed. Please try again.'

export default function DashboardPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [deleting, setDeleting] = useState(false)
  const [confirm, setConfirm] = useState<Workflow | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const mounted = useRef(true)
  const removing = useRef(false)
  const write = useRef<AbortController | null>(null)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; write.current?.abort() }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    listWorkflows(controller.signal).then((items) => {
      if (!controller.signal.aborted) setWorkflows(items)
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) setError(errorMessage(failure))
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [refresh])

  const remove = async () => {
    if (!confirm || removing.current) return
    const id = confirm.id
    const controller = new AbortController()
    write.current = controller
    removing.current = true
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteWorkflow(id, controller.signal)
      if (!controller.signal.aborted && mounted.current) {
        setWorkflows((current) => current.filter((item) => item.id !== id))
        setConfirm(null)
        setRefresh((value) => value + 1)
      }
    } catch (failure) {
      if (!controller.signal.aborted && mounted.current) setDeleteError(errorMessage(failure))
    } finally {
      removing.current = false
      if (mounted.current) setDeleting(false)
    }
  }

  return (
    <div className="workflow-editor dashboard-page">
      <header className="editor-toolbar dashboard-toolbar">
        <a className="editor-brand" href="/" aria-label="FlowPilot Dashboard"><svg viewBox="0 0 36 36" fill="none" aria-hidden="true"><rect width="36" height="36" rx="11" fill="currentColor" /><path d="M11 25V11h14M11 18h10" stroke="#10201c" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><circle cx="25" cy="25" r="3" fill="#10201c" /></svg><span>FlowPilot</span></a>
        <nav className="dashboard-navigation" aria-label="Main navigation"><a href="/" aria-current="page">Dashboard</a><a href="/editor">Workflow Editor</a><a href="/home">Project overview</a></nav>
        <BackendStatus compact />
      </header>
      <main className="dashboard-content">
        <div className="dashboard-heading"><div><p className="eyebrow">YOUR AUTOMATION WORKSPACE</p><h1>Workflows</h1><p className="muted">Create, edit and manage your automation workflows.</p></div><div className="dashboard-actions"><button type="button" className="secondary-button" disabled={loading || deleting} onClick={() => setRefresh((value) => value + 1)}>Refresh workflows</button><a className="primary-button" href="/editor"><span aria-hidden="true">＋</span>Create Workflow</a></div></div>
        {loading && <p role="status">Loading workflows…</p>}
        {error && <div className="dashboard-error" role="alert"><p>{error}</p><button type="button" className="secondary-button" onClick={() => setRefresh((value) => value + 1)}>Retry workflows</button></div>}
        {!loading && !error && workflows.length === 0 && <section className="dashboard-empty"><span aria-hidden="true">＋</span><h2>No workflows yet.</h2><p>Start with a trigger, connect your nodes and save your first workflow.</p><a className="primary-button" href="/editor">Create your first workflow</a></section>}
        {!loading && !error && workflows.length > 0 && <>
          <div className="dashboard-list-heading"><span>{workflows.length} workflow{workflows.length === 1 ? '' : 's'}</span><span className="muted">Schedule and execution status are available in each editor.</span></div>
          <div className="dashboard-table-wrap"><table className="dashboard-table"><thead><tr><th scope="col">Workflow</th><th scope="col">Trigger</th><th scope="col">Nodes</th><th scope="col">Updated</th><th scope="col">Actions</th></tr></thead><tbody>{workflows.map((workflow) => <tr key={workflow.id}>
            <td><strong>{workflow.name}</strong><p>{workflow.description || 'No description'}</p></td>
            <td><span className="trigger-tag">{triggerLabel(workflow)}</span></td><td>{workflow.definition.nodes.length}</td><td><time dateTime={workflow.updated_at}>{updatedAt(workflow.updated_at)}</time></td>
            <td><div className="dashboard-row-actions"><a className="secondary-button" href={`/editor?id=${encodeURIComponent(workflow.id)}`} aria-label={`Open Editor for ${workflow.name}`}>Open Editor</a><button type="button" className="danger-button" aria-label={`Delete ${workflow.name}`} disabled={deleting} onClick={() => { setDeleteError(null); setConfirm(workflow) }}>Delete</button></div></td>
          </tr>)}</tbody></table></div>
        </>}
      </main>
      <footer className="editor-footer"><span>FlowPilot · Self-hosted automation</span><span className="muted">Workflow status is loaded on demand. No background polling.</span></footer>
      {confirm && <Modal title="Delete workflow?" onClose={() => { if (!deleting) setConfirm(null) }}><div className="modal-content"><p>Delete “{confirm.name}”? This permanently removes the workflow, its schedule and execution history.</p>{deleteError && <p role="alert" className="field-error">{deleteError}</p>}<div className="modal-actions"><button type="button" className="secondary-button" disabled={deleting} onClick={() => setConfirm(null)}>Cancel</button><button type="button" className="danger-button" disabled={deleting} onClick={() => { void remove() }}>{deleting ? 'Deleting…' : 'Delete workflow'}</button></div></div></Modal>}
    </div>
  )
}
