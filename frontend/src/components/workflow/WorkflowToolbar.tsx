interface WorkflowToolbarProps {
  name: string
  busy: boolean
  persisted: boolean
  onNameChange: (name: string) => void
  onNew: () => void
  onOpen: () => void
  onSave: () => void
  onDelete: () => void
  onValidate: () => void
  onRun?: () => void
  running?: boolean
}

export default function WorkflowToolbar({
  name, busy, persisted, onNameChange, onNew, onOpen, onSave, onDelete, onValidate, onRun, running = false,
}: WorkflowToolbarProps) {
  return (
    <header className="editor-toolbar">
      <a href="/home" className="editor-brand" aria-label="FlowPilot home">
        <svg aria-hidden="true" viewBox="0 0 36 36" fill="none"><rect width="36" height="36" rx="11" fill="currentColor" /><path d="M11 25V11h14M11 18h10" stroke="#10201c" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /><circle cx="25" cy="25" r="3" fill="#10201c" /></svg>
        <span>FlowPilot</span>
      </a>
      <div className="workflow-title">
        <label htmlFor="workflow-name">WORKFLOW /</label>
        <input id="workflow-name" aria-label="Workflow name" value={name} onChange={(event) => onNameChange(event.target.value)} placeholder="Untitled Workflow" />
      </div>
      <nav aria-label="Workflow actions" className="workflow-actions">
        <a className="toolbar-button" href="/">Dashboard</a>
        <button type="button" className="toolbar-button" onClick={onNew} disabled={busy}><span aria-hidden="true">＋</span>New Workflow</button>
        <button type="button" className="toolbar-button" onClick={onOpen} disabled={busy}>Open Workflow</button>
        <button type="button" className="toolbar-button secondary-action" onClick={onValidate} disabled={busy || !persisted}>Validate</button>
        <button type="button" className="toolbar-button secondary-action" onClick={onDelete} disabled={busy || !persisted}>Delete Workflow</button>
        <button type="button" className="primary-button" onClick={onSave} disabled={busy}><svg aria-hidden="true" viewBox="0 0 20 20" fill="none"><path d="M4 3h10l3 3v11H3V3h1Zm2 0v5h7V3M6 17v-6h8v6" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" /></svg>Save Workflow</button>
        {onRun && <button type="button" className="primary-button run-button" onClick={onRun} disabled={busy || running}><span aria-hidden="true">▶</span>{running ? 'Running' : 'Run Workflow'}</button>}
      </nav>
    </header>
  )
}
