import type { CSSProperties } from 'react'
import type { NodeTypeMetadata } from '../../types/workflow'
import NodeIcon from './NodeIcon'
import { CATEGORY_PRESENTATION, FLOWPILOT_NODE_MIME, nodeCategory, type NodeCategory } from './nodePresentation'

export interface NodeLibraryProps {
  metadata: NodeTypeMetadata[]
  loading: boolean
  error: string | null
  onRetry: () => void
  onAdd: (type: string) => void
}

export default function NodeLibrary({ metadata, loading, error, onRetry, onAdd }: NodeLibraryProps) {
  const categories = Object.keys(CATEGORY_PRESENTATION) as NodeCategory[]
  return (
    <aside className="node-library" aria-labelledby="node-library-title">
      <div className="panel-heading">
        <div><p className="eyebrow">BUILD YOUR WORKFLOW</p><h2 id="node-library-title">Node Library</h2></div>
        <span className="count-badge" aria-label={`${metadata.length} available node types`}>{metadata.length}</span>
      </div>
      <p className="library-help muted">Drag a node onto the canvas, or click to add.</p>
      {loading && <p role="status" className="library-message muted">Loading available nodes…</p>}
      {error && <div className="library-message"><p role="alert">{error}</p><button type="button" className="secondary-button" onClick={onRetry}>Retry node library</button></div>}
      {!loading && !error && metadata.length === 0 && <p className="library-message muted">The backend has no registered node types.</p>}
      {categories.map((category) => {
        const items = metadata.filter((item) => nodeCategory(item.type, item) === category)
        if (items.length === 0) return null
        return (
          <section key={category} className={`library-group category-${category}`} aria-labelledby={`category-${category}`}
            style={{ '--node-accent': CATEGORY_PRESENTATION[category].color } as CSSProperties}>
            <h3 id={`category-${category}`} className="library-category"><span aria-hidden="true" />{CATEGORY_PRESENTATION[category].label}</h3>
            <div className="library-items">
              {items.map((item) => (
                <button type="button" key={item.type} className="library-node" draggable
                  data-node-type={item.type} aria-label={`Add ${item.display_name}`}
                  title={`Drag ${item.display_name} onto the canvas, or click to add`}
                  onClick={() => onAdd(item.type)}
                  onDragStart={(event) => {
                    event.dataTransfer.setData(FLOWPILOT_NODE_MIME, item.type)
                    event.dataTransfer.effectAllowed = 'copy'
                  }}>
                  <span className="library-node-icon"><NodeIcon type={item.type} /></span>
                  <span className="library-node-content"><strong>{item.display_name}</strong><span>{item.description}</span></span>
                  <span className="library-add" aria-hidden="true">+</span>
                </button>
              ))}
            </div>
          </section>
        )
      })}
      <div className="library-footnote muted">Node availability comes from your backend registry.</div>
    </aside>
  )
}
