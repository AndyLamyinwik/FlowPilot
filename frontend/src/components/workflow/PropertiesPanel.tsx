import { useId } from 'react'
import type { FlowEdge, FlowNode, JsonObject, JsonValue, NodeTypeMetadata } from '../../types/workflow'
import { getAncestorNodes } from '../../utils/workflowGraph'
import { isJsonObject, jsonText, parseConfigJson, validateHeaders } from './configForms'

export interface PropertiesPanelProps {
  node: FlowNode | null
  nodes: FlowNode[]
  edges: FlowEdge[]
  metadata: NodeTypeMetadata[]
  drafts: Record<string, string>
  onDraftChange: (field: string, text: string, error: string | null) => void
  onChange: (nodeId: string, updates: { name?: string; config?: JsonObject }) => void
  onDelete: (nodeId: string) => void
}

const operators = [
  'equals', 'not_equals', 'greater_than', 'greater_than_or_equal',
  'less_than', 'less_than_or_equal', 'contains', 'exists',
]
const supportedTypes = new Set([
  'trigger.manual', 'trigger.schedule', 'action.http_request', 'logic.condition',
  'data.transform', 'action.webhook', 'utility.logger',
])

function textValue(value: JsonValue | undefined, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

interface JsonFieldProps {
  label: string
  field: string
  value: JsonValue | undefined
  drafts: Record<string, string>
  objectOnly?: boolean
  optional?: boolean
  headers?: boolean
  help?: string
  onDraftChange: PropertiesPanelProps['onDraftChange']
  onValue: (value: JsonValue | undefined) => void
}

function JsonField({
  label, field, value, drafts, objectOnly = false, optional = false,
  headers = false, help, onDraftChange, onValue,
}: JsonFieldProps) {
  const id = useId()
  const text = Object.hasOwn(drafts, field) ? drafts[field] : jsonText(value)
  const parse = (source: string) => {
    if (optional && source.trim() === '') return { value: undefined, error: null }
    const parsed = parseConfigJson(source, objectOnly)
    if (parsed.error) return parsed
    const error = headers ? validateHeaders(parsed.value!) : null
    return error ? { error } : parsed
  }
  const parsed = parse(text)
  return (
    <div className="form-field">
      <label className="field-label" htmlFor={id}>{label}</label>
      <textarea
        className="field-textarea" id={id} value={text} rows={headers ? 5 : 8}
        spellCheck={false} aria-invalid={Boolean(parsed.error)}
        aria-describedby={`${id}-help${parsed.error ? ` ${id}-error` : ''}`}
        onChange={(event) => {
          const next = event.target.value
          const result = parse(next)
          onDraftChange(field, next, result.error)
          if (!result.error) onValue(result.value)
        }}
      />
      <p className="field-help" id={`${id}-help`}>{help || 'Use JSON. Changes are saved only when you click Save.'}</p>
      {parsed.error && <p className="field-error" id={`${id}-error`} role="alert">{parsed.error}</p>}
    </div>
  )
}

interface SourceFieldProps {
  node: FlowNode
  nodes: FlowNode[]
  edges: FlowEdge[]
  onChange: (source: string) => void
}

function SourceField({ node, nodes, edges, onChange }: SourceFieldProps) {
  const id = useId()
  const ancestors = getAncestorNodes(node.id, nodes, edges)
  const selected = textValue(node.data.config.source_node_id)
  const unavailable = selected !== '' && !ancestors.some((item) => item.id === selected)
  return (
    <div className="form-field">
      <label className="field-label" htmlFor={id}>Source node</label>
      <select className="field-select" id={id} value={selected} onChange={(event) => onChange(event.target.value)}>
        <option value="">Choose an upstream node</option>
        {unavailable && <option value={selected}>{selected} (not an upstream node)</option>}
        {ancestors.map((item) => <option key={item.id} value={item.id}>{item.data.name} · {item.id}</option>)}
      </select>
      <p className="field-help">Connect nodes first. Only ancestors in this workflow are available.</p>
      {unavailable && <p className="field-help">The existing reference is preserved, but it must be upstream before execution.</p>}
    </div>
  )
}

export default function PropertiesPanel({
  node, nodes, edges, metadata, drafts, onDraftChange, onChange, onDelete,
}: PropertiesPanelProps) {
  const id = useId()
  if (!node) {
    return (
      <aside className="properties-panel" aria-label="Properties panel">
        <div className="panel-heading"><h2>Properties</h2><span>Node configuration</span></div>
        <div className="empty-panel"><h3>Select a node</h3><p>Choose a node on the canvas to edit its name and configuration.</p></div>
      </aside>
    )
  }
  const config = node.data.config
  const nodeType = node.data.nodeType
  const nodeMetadata = metadata.find((item) => item.type === nodeType) ?? node.data.metadata
  const known = supportedTypes.has(nodeType)
  const setConfig = (key: string, value: JsonValue | undefined) => {
    const next = { ...config }
    if (value === undefined) delete next[key]
    else next[key] = value
    onChange(node.id, { config: next })
  }
  const field = (label: string, key: string, placeholder = '', help?: string) => (
    <div className="form-field" key={key}>
      <label className="field-label" htmlFor={`${id}-${key}`}>{label}</label>
      <input
        className="field-input" id={`${id}-${key}`} value={textValue(config[key])}
        placeholder={placeholder} spellCheck={false}
        onChange={(event) => setConfig(key, event.target.value)}
      />
      {help && <p className="field-help">{help}</p>}
    </div>
  )
  const timeout = (
    <div className="form-field">
      <label className="field-label" htmlFor={`${id}-timeout`}>Timeout (seconds)</label>
      <input
        className="field-input" id={`${id}-timeout`} type="number" min="0" max="60" step="any"
        value={typeof config.timeout === 'number' || typeof config.timeout === 'string' ? config.timeout : ''}
        placeholder="10" onChange={(event) => setConfig('timeout', event.target.value === '' ? undefined : Number(event.target.value))}
      />
      <p className="field-help">Execution requires a timeout greater than 0 and at most 60 seconds. Omit to use 10.</p>
    </div>
  )
  const headers = (
    <JsonField
      label="Headers (JSON)" field="headers" value={config.headers ?? {}} drafts={drafts}
      objectOnly optional headers onDraftChange={onDraftChange}
      onValue={(value) => setConfig('headers', value)}
      help="String values only. Authorization, cookies, API keys and client-managed headers are not allowed."
    />
  )

  return (
    <aside className="properties-panel" aria-label="Properties panel">
      <div className="panel-heading"><h2>Properties</h2><span>Node configuration</span></div>
      <div className="properties-content">
        <div className="form-field">
          <label className="field-label" htmlFor={`${id}-name`}>Node name</label>
          <input className="field-input" id={`${id}-name`} value={node.data.name} onChange={(event) => onChange(node.id, { name: event.target.value })} />
        </div>
        <div className="form-field"><span className="field-label">Node type</span><code className="node-type-label">{nodeType}</code></div>
        <p className="field-help">{nodeMetadata?.description ?? 'This node type does not yet have a configuration form.'}</p>
        <p className="field-help node-id">ID: {node.id}</p>

        {nodeType === 'trigger.schedule' && <>
          {field('Cron expression', 'cron', '0 9 * * *', 'Five fields. APScheduler uses Monday=0; prefer mon–sun names.')}
          {field('Timezone', 'timezone', 'UTC', 'IANA timezone, for example UTC or Asia/Singapore.')}
        </>}

        {nodeType === 'action.http_request' && <>
          <div className="form-field">
            <label className="field-label" htmlFor={`${id}-method`}>Method</label>
            <select className="field-select" id={`${id}-method`} value={textValue(config.method, 'GET')} onChange={(event) => {
              const next: JsonObject = { ...config, method: event.target.value }
              const bodyText = Object.hasOwn(drafts, 'body') ? drafts.body : jsonText(config.body)
              if (event.target.value === 'GET') {
                delete next.body
                // A hidden field is omitted from config, but its unfinished text
                // remains available if the user switches back to POST.
                onDraftChange('body', bodyText, null)
              } else {
                const parsed = bodyText.trim() === ''
                  ? { value: undefined, error: null } : parseConfigJson(bodyText)
                onDraftChange('body', bodyText, parsed.error)
                if (!parsed.error && parsed.value !== undefined) next.body = parsed.value
              }
              onChange(node.id, { config: next })
            }}>
              {config.method !== undefined && config.method !== 'GET' && config.method !== 'POST' && <option value={String(config.method)}>Unsupported: {String(config.method)}</option>}
              <option value="GET">GET</option><option value="POST">POST</option>
            </select>
          </div>
          {field('URL', 'url', 'https://example.com/data', 'The backend host allowlist and network restrictions still apply.')}
          {headers}{timeout}
          {config.method === 'POST' && <JsonField
            label="Request body (JSON)" field="body" value={config.body} drafts={drafts}
            optional onDraftChange={onDraftChange} onValue={(value) => setConfig('body', value)}
            help="Leave blank to omit the body. Enter null to send JSON null."
          />}
        </>}

        {nodeType === 'logic.condition' && <>
          <SourceField node={node} nodes={nodes} edges={edges} onChange={(source) => setConfig('source_node_id', source)} />
          {field('Field path', 'field', 'body.user.name', 'Dot-separated object keys and nonnegative array indexes. Blank selects the whole output.')}
          <div className="form-field">
            <label className="field-label" htmlFor={`${id}-operator`}>Operator</label>
            <select className="field-select" id={`${id}-operator`} value={textValue(config.operator, 'exists')} onChange={(event) => {
              const next: JsonObject = { ...config, operator: event.target.value }
              const valueText = Object.hasOwn(drafts, 'value') ? drafts.value : jsonText(config.value)
              if (event.target.value === 'exists') {
                delete next.value
                onDraftChange('value', valueText, null)
              } else {
                const parsed = valueText.trim() === ''
                  ? { value: undefined, error: null } : parseConfigJson(valueText)
                onDraftChange('value', valueText, parsed.error)
                if (!parsed.error && parsed.value !== undefined) next.value = parsed.value
              }
              onChange(node.id, { config: next })
            }}>
              {config.operator !== undefined && !operators.includes(String(config.operator)) && <option value={String(config.operator)}>Unsupported: {String(config.operator)}</option>}
              {operators.map((operator) => <option key={operator} value={operator}>{operator}</option>)}
            </select>
          </div>
          {textValue(config.operator, 'exists') !== 'exists' && <JsonField
            label="Compare value (JSON)" field="value" value={config.value} drafts={drafts}
            optional onDraftChange={onDraftChange} onValue={(value) => setConfig('value', value)}
            help={'Use JSON: "text", 42, true or null. Leave blank for an unfinished draft.'}
          />}
          <p className="field-help">True and false routes are connected using the node handles on the canvas.</p>
        </>}

        {nodeType === 'data.transform' && <JsonField
          label="Mapping configuration (JSON)" field="mapping" value={config} drafts={drafts}
          objectOnly onDraftChange={onDraftChange}
          onValue={(value) => { if (isJsonObject(value)) onChange(node.id, { config: value }) }}
          help={'Enter the complete config, for example {"mapping":{"source":{"value":"FlowPilot"}}}.'}
        />}

        {nodeType === 'action.webhook' && <>
          {field('URL', 'url', 'https://example.com/notify', 'Sends an outgoing POST; it does not create an incoming webhook.')}
          <SourceField node={node} nodes={nodes} edges={edges} onChange={(source) => setConfig('source_node_id', source)} />
          {field('Field path', 'path', 'body.result', 'Optional. Leave blank to send the entire referenced output.')}
          {headers}{timeout}
        </>}

        {(nodeType === 'trigger.manual' || nodeType === 'utility.logger') && <p className="field-help">This node needs no additional configuration.</p>}
        {!known && <div className="form-field">
          <label className="field-label" htmlFor={`${id}-unknown`}>Configuration (read-only)</label>
          <textarea className="field-textarea" id={`${id}-unknown`} value={jsonText(config)} rows={10} readOnly />
          <p className="field-help">This configuration is preserved when you save. Editing for this node type is not supported yet.</p>
        </div>}
        <button type="button" className="danger-button" onClick={() => onDelete(node.id)}>Delete node</button>
      </div>
    </aside>
  )
}
