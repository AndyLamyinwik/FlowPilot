import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ReactFlowProvider, addEdge, useEdgesState, useNodesState,
  type Connection, type EdgeChange, type NodeChange, type ReactFlowInstance, type XYPosition,
} from '@xyflow/react'
import BackendStatus from '../components/BackendStatus'
import Modal from '../components/ui/Modal'
import NodeLibrary from '../components/workflow/NodeLibrary'
import PropertiesPanel from '../components/workflow/PropertiesPanel'
import WorkflowCanvas from '../components/workflow/WorkflowCanvas'
import WorkflowToolbar from '../components/workflow/WorkflowToolbar'
import {
  createWorkflow, deleteWorkflow, getNodeTypes, getWorkflow, listWorkflows,
  updateWorkflow,
} from '../services/workflowApi'
import useWorkflowExecution from '../hooks/useWorkflowExecution'
import ExecutionPanel from '../components/execution/ExecutionPanel'
import ExecutionHistory from '../components/execution/ExecutionHistory'
import ValidationPanel from '../components/execution/ValidationPanel'
import ExecutionStatus from '../components/execution/ExecutionStatus'
import SchedulePanel from '../components/schedule/SchedulePanel'
import type { FlowEdge, FlowNode, JsonObject, NodeTypeMetadata, ValidationIssue, Workflow } from '../types/workflow'
import { toReactFlow, toWorkflowDefinition } from '../utils/workflowAdapter'
import { createFlowNode, validateConnection } from '../utils/workflowGraph'

interface Confirmation { title: string; detail: string; label: string; action: () => void }
type Buffers = Record<string, Record<string, string>>
const errorMessage = (error: unknown) => error instanceof Error ? error.message : 'The request could not be completed. Please try again.'

function Editor({ initialWorkflowId }: { initialWorkflowId?: string | null }) {
  const [nodes, setNodes, applyNodesChange] = useNodesState<FlowNode>([])
  const [edges, setEdges, applyEdgesChange] = useEdgesState<FlowEdge>([])
  const [name, setName] = useState('Untitled Workflow')
  const [description, setDescription] = useState<string | null>('')
  const [workflowId, setWorkflowId] = useState<string | null>(null)
  const [schemaVersion, setSchemaVersion] = useState<1>(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [metadata, setMetadata] = useState<NodeTypeMetadata[]>([])
  const [registryLoading, setRegistryLoading] = useState(true)
  const [registryError, setRegistryError] = useState<string | null>(null)
  const [registryRequest, setRegistryRequest] = useState(0)
  const [drafts, setDrafts] = useState<Buffers>({})
  const [draftErrors, setDraftErrors] = useState<Buffers>({})
  const [revision, setRevision] = useState(0)
  const [savedRevision, setSavedRevision] = useState(0)
  const [busy, setBusy] = useState<'save' | 'load' | 'delete' | 'validate' | null>(null)
  const [saveFailed, setSaveFailed] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'info'; text: string } | null>(null)
  const [open, setOpen] = useState(false)
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [listLoading, setListLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const [epoch, setEpoch] = useState(0)
  const [historyRefresh, setHistoryRefresh] = useState(0)
  const [scheduleRefresh, setScheduleRefresh] = useState(0)
  const [panel, setPanel] = useState<'properties' | 'execution' | 'history' | 'schedule' | 'validation'>('properties')
  const [visitedHistory, setVisitedHistory] = useState(false)
  const [visitedSchedule, setVisitedSchedule] = useState(false)
  const [scheduleIssues, setScheduleIssues] = useState<ValidationIssue[]>([])
  const revisionRef = useRef(0)
  const instance = useRef<ReactFlowInstance<FlowNode, FlowEdge> | null>(null)
  const canvasRef = useRef<HTMLDivElement>(null)
  const mounted = useRef(true)
  const registryController = useRef<AbortController | null>(null)
  const operationController = useRef<AbortController | null>(null)
  const listController = useRef<AbortController | null>(null)
  const dirty = revision !== savedRevision
  const selected = nodes.find((node) => node.id === selectedId) ?? null
  const invalidBuffers = nodes.some((node) => Object.keys(draftErrors[node.id] ?? {}).length > 0)
  const metadataRef = useRef(metadata)
  metadataRef.current = metadata
  const execution = useWorkflowExecution({
    workflowId, workflowName: name, nodes, dirty: dirty || invalidBuffers,
    revision, epoch, onNotice: setMessage,
    onComplete: () => setHistoryRefresh((value) => value + 1),
  })

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      registryController.current?.abort()
      operationController.current?.abort()
      listController.current?.abort()
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    registryController.current = controller
    setRegistryLoading(true)
    setRegistryError(null)
    getNodeTypes(controller.signal).then((items) => {
      if (controller.signal.aborted) return
      metadataRef.current = items
      setMetadata(items)
      // Presentation metadata is not part of the persisted workflow or dirty state.
      setNodes((current) => current.map((node) => ({ ...node, data: {
        ...node.data, metadata: items.find((item) => item.type === node.data.nodeType),
      } })))
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setRegistryError(errorMessage(error))
    }).finally(() => { if (!controller.signal.aborted) setRegistryLoading(false) })
    return () => controller.abort()
  }, [registryRequest, setNodes])

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (!dirty && busy !== 'save' && !execution.running) return
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, busy, execution.running])

  const changed = useCallback(() => {
    revisionRef.current += 1
    setRevision(revisionRef.current)
    setSaveFailed(false)
    setMessage(null)
    setScheduleIssues([])
  }, [])

  const replaceWorkflow = (workflow: Workflow | null) => {
    const graph = workflow ? toReactFlow(workflow.definition, metadataRef.current) : { nodes: [], edges: [], schemaVersion: 1 as const }
    setEpoch((value) => value + 1)
    setPanel('properties')
    setVisitedHistory(false)
    setVisitedSchedule(false)
    setScheduleIssues([])
    setNodes(graph.nodes)
    setEdges(graph.edges)
    setName(workflow?.name ?? 'Untitled Workflow')
    setDescription(workflow?.description ?? '')
    setWorkflowId(workflow?.id ?? null)
    setSchemaVersion(graph.schemaVersion)
    setSelectedId(null)
    setDrafts({})
    setDraftErrors({})
    revisionRef.current = 0
    setRevision(0)
    setSavedRevision(0)
    setSaveFailed(false)
    const unsupportedConnection = graph.edges.some((edge) => {
      const source = graph.nodes.find((node) => node.id === edge.source)
      const target = graph.nodes.find((node) => node.id === edge.target)
      return edge.targetHandle != null
        || (source?.data.nodeType === 'logic.condition'
          ? !['true', 'false'].includes(edge.sourceHandle ?? '') : edge.sourceHandle != null)
        || target?.data.nodeType.startsWith('trigger.') || target?.data.metadata?.category === 'trigger'
    })
    setMessage(unsupportedConnection ? { kind: 'info', text: 'This draft contains connections with unsupported handles or trigger inputs. Their data is preserved, but some connections may not be displayed.' } : null)
    requestAnimationFrame(() => { void instance.current?.fitView({ padding: 0.25, maxZoom: 1 }) })
  }

  const discardThen = (action: () => void) => {
    if (!dirty) { action(); return }
    setConfirmation({ title: 'Discard unsaved changes?', detail: 'Your changes have not been saved. Discard them to continue.', label: 'Discard changes', action })
  }

  const refreshList = async () => {
    listController.current?.abort()
    const controller = new AbortController()
    listController.current = controller
    setListLoading(true)
    setListError(null)
    try {
      const items = await listWorkflows(controller.signal)
      if (!controller.signal.aborted) setWorkflows(items)
    } catch (error) {
      if (!controller.signal.aborted) setListError(errorMessage(error))
    } finally {
      if (!controller.signal.aborted) setListLoading(false)
    }
  }

  const load = async (id: string) => {
    const loadingRevision = revisionRef.current
    setOpen(false)
    setBusy('load')
    const controller = new AbortController()
    operationController.current = controller
    try {
      const workflow = await getWorkflow(id, controller.signal)
      if (controller.signal.aborted || !mounted.current) return
      if (revisionRef.current !== loadingRevision) {
        setMessage({ kind: 'info', text: 'Load canceled because editing continued. Your changes are kept; open the workflow again when ready.' })
        return
      }
      replaceWorkflow(workflow)
    } catch (error) {
      if (!controller.signal.aborted) setMessage({ kind: 'error', text: `Load failed. ${errorMessage(error)}` })
    } finally { if (!controller.signal.aborted && mounted.current) setBusy(null) }
  }

  const save = async () => {
    if (invalidBuffers) {
      setSaveFailed(true)
      setMessage({ kind: 'error', text: 'Save failed. Fix invalid JSON or forbidden headers in the Properties panel. Your input has been kept.' })
      return
    }
    let definition
    try {
      if (!name.trim()) throw new Error('Enter a workflow name before saving.')
      definition = toWorkflowDefinition(nodes, edges, schemaVersion)
    } catch (error) {
      setSaveFailed(true)
      setMessage({ kind: 'error', text: `Save failed. ${errorMessage(error)}` })
      return
    }
    const savingRevision = revisionRef.current
    const payload = { name, description, definition }
    const controller = new AbortController()
    operationController.current = controller
    setBusy('save')
    setSaveFailed(false)
    setMessage(null)
    try {
      const saved = workflowId
        ? await updateWorkflow(workflowId, payload, controller.signal)
        : await createWorkflow(payload, controller.signal)
      if (controller.signal.aborted || !mounted.current) return
      setWorkflowId(saved.id)
      setScheduleRefresh((value) => value + 1)
      setScheduleIssues([])
      setSavedRevision(savingRevision)
      // Edits made while the request is in flight stay in the editor and stay dirty.
      if (revisionRef.current === savingRevision) {
        const graph = toReactFlow(saved.definition, metadata)
        setNodes((current) => graph.nodes.map((node) => ({ ...node, selected: current.find((item) => item.id === node.id)?.selected })))
        setEdges((current) => graph.edges.map((edge) => ({ ...edge, selected: current.find((item) => item.id === edge.id)?.selected })))
        setName(saved.name)
        setDescription(saved.description)
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setSaveFailed(true)
        setMessage({ kind: 'error', text: `Save failed. ${errorMessage(error)}` })
      }
    } finally { if (!controller.signal.aborted && mounted.current) setBusy(null) }
  }

  const removeWorkflow = async () => {
    if (!workflowId) return
    const deletingRevision = revisionRef.current
    const controller = new AbortController()
    operationController.current = controller
    setBusy('delete')
    try {
      await deleteWorkflow(workflowId, controller.signal)
      if (!controller.signal.aborted && mounted.current) {
        if (revisionRef.current === deletingRevision) replaceWorkflow(null)
        else {
          setWorkflowId(null)
          setMessage({ kind: 'info', text: 'Workflow deleted. Changes made during deletion are kept as a new unsaved draft.' })
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) setMessage({ kind: 'error', text: `Delete failed. ${errorMessage(error)}` })
    } finally { if (!controller.signal.aborted && mounted.current) setBusy(null) }
  }

  useEffect(() => {
    if (initialWorkflowId) void load(initialWorkflowId)
    return () => operationController.current?.abort()
    // URL navigation remounts the editor; this effect owns the initial load only.
  }, [initialWorkflowId])

  const addNode = (type: string, position?: XYPosition) => {
    const item = metadata.find((entry) => entry.type === type)
    if (!item) { setMessage({ kind: 'error', text: 'This node type is not available in the backend registry.' }); return }
    const rect = canvasRef.current?.getBoundingClientRect()
    const offset = (nodes.length % 4) * 40
    const location = position ?? (instance.current && rect
      ? instance.current.screenToFlowPosition({ x: rect.left + rect.width / 2 + offset, y: rect.top + rect.height / 2 + offset })
      : { x: 100 + offset, y: 100 + offset })
    const node = createFlowNode(item, location)
    setNodes((current) => [...current.map((entry) => ({ ...entry, selected: false })), { ...node, selected: true }])
    setSelectedId(node.id)
    changed()
  }

  const onNodesChange = (changes: NodeChange<FlowNode>[]) => {
    const dataChange = changes.some((change) => change.type === 'remove' || change.type === 'add' || change.type === 'replace'
      || (change.type === 'position' && change.position && nodes.some((node) => node.id === change.id
        && (node.position.x !== change.position!.x || node.position.y !== change.position!.y))))
    const removed = new Set(changes.filter((change) => change.type === 'remove').map((change) => change.id))
    if (removed.size) {
      setEdges((current) => current.filter((edge) => !removed.has(edge.source) && !removed.has(edge.target)))
      setDrafts((current) => Object.fromEntries(Object.entries(current).filter(([id]) => !removed.has(id))))
      setDraftErrors((current) => Object.fromEntries(Object.entries(current).filter(([id]) => !removed.has(id))))
    }
    applyNodesChange(changes)
    if (dataChange) changed()
  }
  const onEdgesChange = (changes: EdgeChange<FlowEdge>[]) => {
    applyEdgesChange(changes)
    if (changes.some((change) => change.type !== 'select')) changed()
  }
  const connect = (connection: Connection) => {
    const error = validateConnection(connection, nodes, edges)
    if (error) { setMessage({ kind: 'error', text: error }); return }
    setEdges((current) => addEdge({ ...connection, id: crypto.randomUUID() }, current))
    changed()
  }
  const removeNode = (id: string) => {
    setNodes((current) => current.filter((node) => node.id !== id))
    setEdges((current) => current.filter((edge) => edge.source !== id && edge.target !== id))
    setSelectedId(null)
    setDrafts((current) => { const next = { ...current }; delete next[id]; return next })
    setDraftErrors((current) => { const next = { ...current }; delete next[id]; return next })
    changed()
  }
  const updateNode = (id: string, updates: { name?: string; config?: JsonObject }) => {
    setNodes((current) => current.map((node) => node.id === id ? { ...node, data: { ...node.data, ...updates } } : node))
    changed()
  }
  const selectedEdges = edges.filter((edge) => edge.selected)
  const statuses = new Map(!execution.stale ? execution.execution?.node_results.map((item) => [item.node_id, item.status]) : [])
  const displayNodes = nodes.map((node) => ({ ...node, data: {
    ...node.data, executionStatus: statuses.get(node.id),
    executionId: !execution.stale ? execution.execution?.execution_id : undefined,
  } }))
  const selectResultNode = (id: string) => {
    if (!nodes.some((node) => node.id === id)) return
    setSelectedId(id)
    setNodes((current) => current.map((node) => ({ ...node, selected: node.id === id })))
    void instance.current?.fitView({ nodes: [{ id }], padding: 0.5, maxZoom: 1 })
  }
  const status = busy === 'save' ? 'Saving' : saveFailed ? 'Save Failed' : dirty || !workflowId ? 'Unsaved Changes' : 'Saved'

  return (
    <div className="workflow-editor">
      <h1 className="sr-only">FlowPilot Workflow Editor</h1>
      <WorkflowToolbar name={name} busy={busy !== null} persisted={workflowId !== null}
        onNameChange={(value) => { setName(value); changed() }}
        onNew={() => discardThen(() => replaceWorkflow(null))}
        onOpen={() => { setOpen(true); void refreshList() }} onSave={() => { void save() }}
        onDelete={() => setConfirmation({ title: 'Delete workflow?', detail: 'This permanently deletes this workflow, its schedule and its execution history. Unsaved changes will also be discarded.', label: 'Delete workflow', action: () => { void removeWorkflow() } })}
        onValidate={() => { setPanel('validation'); void execution.validate() }}
        onRun={() => { setPanel('execution'); void execution.run() }} running={execution.running || execution.validating} />
      <div className="editor-context-bar"><div><span className="editor-context-dot" />Visual editor<span className="context-divider">/</span><span className="muted">Draft workspace</span></div><BackendStatus compact /></div>
      {message && <div className={`editor-message ${message.kind}`} role={message.kind === 'error' ? 'alert' : 'status'}><span>{message.text}</span><button type="button" className="icon-button" aria-label="Dismiss message" onClick={() => setMessage(null)}>×</button></div>}
      <main className="editor-workspace">
        <NodeLibrary metadata={metadata} loading={registryLoading} error={registryError} onRetry={() => setRegistryRequest((value) => value + 1)} onAdd={addNode} />
        <div className="canvas-column" ref={canvasRef}>
          <div className="canvas-heading"><span>Workflow canvas</span><span>{nodes.length} nodes<span className="context-divider">·</span>{edges.length} connections</span></div>
          <WorkflowCanvas nodes={displayNodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            onConnect={connect} isValidConnection={(connection) => validateConnection(connection, nodes, edges) === null}
            onSelectionChange={({ nodes: selectedNodes }) => setSelectedId(selectedNodes[0]?.id ?? null)}
            onDropNode={addNode} onInit={(flow) => { instance.current = flow }} />
          <div className="canvas-help"><span>Drag to pan · Scroll to zoom · Delete to remove selection</span>{selectedEdges.length > 0 && <button type="button" onClick={() => { setEdges((current) => current.filter((edge) => !edge.selected)); changed() }}>Delete selected connection{selectedEdges.length > 1 ? 's' : ''}</button>}</div>
        </div>
        <aside className="editor-side-panel" aria-label="Workflow inspector">
          <nav className="inspector-tabs" aria-label="Inspector views">{(['properties', 'execution', 'history', 'schedule', 'validation'] as const).map((tab) => <button key={tab} type="button" aria-pressed={panel === tab} onClick={() => {
            setPanel(tab)
            if (tab === 'history') setVisitedHistory(true)
            if (tab === 'schedule') setVisitedSchedule(true)
          }}>{tab[0].toUpperCase() + tab.slice(1)}</button>)}</nav>
          <div hidden={panel !== 'properties'}><PropertiesPanel node={selected} nodes={nodes} edges={edges} metadata={metadata} drafts={selected ? drafts[selected.id] ?? {} : {}}
          onChange={updateNode} onDelete={removeNode} onDraftChange={(field, text, error) => {
            if (!selected) return
            setDrafts((current) => ({ ...current, [selected.id]: { ...current[selected.id], [field]: text } }))
            setDraftErrors((current) => {
              const next = { ...current[selected.id] }
              if (error) next[field] = error
              else delete next[field]
              return { ...current, [selected.id]: next }
            })
            changed()
          }} /></div>
          {panel === 'execution' && <div className="inspector-content">
            {execution.validating && <p role="status">Checking the saved graph before execution…</p>}
            {execution.running && <p role="status"><ExecutionStatus status="running" /> Waiting for the backend. Node states appear when the response arrives.</p>}
            {execution.stale && <p className="field-help">Workflow changed since this execution. These results belong to the earlier saved version; canvas badges have been cleared.</p>}
            {(execution.issues.length > 0 || (execution.report && (!execution.report.structural.valid || !execution.report.execution_readiness.valid))) && <ValidationPanel report={execution.report} issues={execution.issues} onSelectNode={selectResultNode} />}
            <ExecutionPanel execution={execution.execution} workflowName={execution.executionName || name} triggerType="manual" selectedNodeId={selectedId}
              nodeNames={execution.executionNodeNames} onSelectNode={selectResultNode} />
          </div>}
          <div hidden={panel !== 'history'}>{visitedHistory && <ExecutionHistory workflowId={workflowId} refreshKey={historyRefresh} />}</div>
          <div hidden={panel !== 'schedule'}>{visitedSchedule && <SchedulePanel workflowId={workflowId} hasSchedule={nodes.some((node) => node.data.nodeType === 'trigger.schedule')}
            dirty={dirty || invalidBuffers || !workflowId} refreshKey={scheduleRefresh} onIssues={setScheduleIssues} />}
            {visitedSchedule && scheduleIssues.length > 0 && <ValidationPanel report={null} issues={scheduleIssues} onSelectNode={selectResultNode} />}</div>
          {panel === 'validation' && <ValidationPanel report={execution.report} issues={execution.issues} onSelectNode={selectResultNode} />}
        </aside>
      </main>
      <footer className="editor-footer"><div role="status" aria-live="polite" className={`save-state ${status === 'Saved' ? 'saved' : saveFailed ? 'failed' : ''}`}><span />{status}</div><p>Drafts can be saved before node configuration is complete.</p><span className="footer-id">{workflowId ? `ID ${workflowId.slice(0, 8)}` : 'New workflow'}</span></footer>
      {open && <Modal title="Open Workflow" onClose={() => { setOpen(false); listController.current?.abort() }}>
        <div className="modal-content">
          {listLoading && <p role="status">Loading workflows…</p>}
          {listError && <div><p role="alert" className="field-error">{listError}</p><button className="secondary-button" type="button" onClick={() => { void refreshList() }}>Retry workflows</button></div>}
          {!listLoading && !listError && workflows.length === 0 && <div className="modal-empty"><h3>No saved workflows yet</h3><p>Create your first workflow on the canvas, then click Save Workflow.</p></div>}
          <ul className="workflow-list">{!listLoading && !listError && workflows.map((workflow) => <li key={workflow.id}><button type="button" disabled={busy !== null} onClick={() => { setOpen(false); discardThen(() => { void load(workflow.id) }) }}><span><strong>{workflow.name}</strong><span>{workflow.definition.nodes.length} nodes · {workflow.definition.edges.length} connections</span></span><span aria-hidden="true">↗</span></button></li>)}</ul>
        </div>
      </Modal>}
      {confirmation && <Modal title={confirmation.title} onClose={() => setConfirmation(null)}><div className="modal-content"><p>{confirmation.detail}</p><div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setConfirmation(null)}>Cancel</button><button type="button" className="danger-button" onClick={() => { const action = confirmation.action; setConfirmation(null); action() }}>{confirmation.label}</button></div></div></Modal>}
    </div>
  )
}

export default function WorkflowEditorPage({ initialWorkflowId }: { initialWorkflowId?: string | null } = {}) {
  return <ReactFlowProvider><Editor initialWorkflowId={initialWorkflowId} /></ReactFlowProvider>
}
