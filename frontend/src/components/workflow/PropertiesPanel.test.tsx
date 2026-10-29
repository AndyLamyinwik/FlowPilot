import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { FlowEdge, FlowNode, JsonObject, NodeTypeMetadata } from '../../types/workflow'
import PropertiesPanel from './PropertiesPanel'
import { parseConfigJson, validateHeaders } from './configForms'

function makeNode(nodeType = 'action.http_request', config: JsonObject = {}): FlowNode {
  return {
    id: 'edited', type: 'flowpilotNode', position: { x: 0, y: 0 },
    data: { nodeType, name: 'My node', config },
  }
}

const ancestor: FlowNode = {
  id: 'upstream', type: 'flowpilotNode', position: { x: 0, y: 0 },
  data: { nodeType: 'trigger.manual', name: 'Manual Trigger', config: {} },
}
const unrelated: FlowNode = {
  id: 'unrelated', type: 'flowpilotNode', position: { x: 0, y: 0 },
  data: { nodeType: 'utility.logger', name: 'Unrelated logger', config: {} },
}
const edges: FlowEdge[] = [{ id: 'incoming', source: ancestor.id, target: 'edited' }]
const registry: NodeTypeMetadata[] = [{
  type: 'action.http_request', display_name: 'HTTP Request', category: 'action',
  description: 'Make an HTTP request',
}]

function EditorHarness({ initial = makeNode() }: { initial?: FlowNode }) {
  const [node, setNode] = useState(initial)
  const [selected, setSelected] = useState(true)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string | null>>({})
  return <>
    <PropertiesPanel
      node={selected ? node : null} nodes={[ancestor, node, unrelated]} edges={edges}
      metadata={registry} drafts={drafts}
      onDraftChange={(field, text, error) => {
        setDrafts((value) => ({ ...value, [field]: text }))
        setErrors((value) => ({ ...value, [field]: error }))
      }}
      onChange={(_, updates) => setNode((value) => ({ ...value, data: { ...value.data, ...updates } }))}
      onDelete={() => setSelected(false)}
    />
    <button onClick={() => setSelected((value) => !value)}>Toggle selection</button>
    <output data-testid="config">{JSON.stringify(node.data.config)}</output>
    <output data-testid="name">{node.data.name}</output>
    <output data-testid="save-state">{Object.values(errors).some(Boolean) ? 'blocked' : 'allowed'}</output>
  </>
}

function config(): JsonObject {
  return JSON.parse(screen.getByTestId('config').textContent!) as JsonObject
}

describe('PropertiesPanel', () => {
  it('shows an accessible empty state and registry description', () => {
    render(<EditorHarness />)
    expect(screen.getByText('Make an HTTP request')).toBeTruthy()
    fireEvent.click(screen.getByText('Toggle selection'))
    expect(screen.getByRole('heading', { name: 'Select a node' })).toBeTruthy()
  })

  it('edits the node name without dropping existing configuration', () => {
    render(<EditorHarness initial={makeNode('utility.logger', { future: { enabled: true } })} />)
    fireEvent.change(screen.getByLabelText('Node name'), { target: { value: 'Renamed logger' } })
    expect(screen.getByTestId('name').textContent).toBe('Renamed logger')
    expect(config()).toEqual({ future: { enabled: true } })
    expect(screen.getByText('This node needs no additional configuration.')).toBeTruthy()
  })

  it('keeps Manual Trigger simple and sends the delete callback', () => {
    render(<EditorHarness initial={makeNode('trigger.manual')} />)
    expect(screen.queryByLabelText('Cron expression')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Delete node' }))
    expect(screen.getByRole('heading', { name: 'Select a node' })).toBeTruthy()
  })

  it('edits Schedule cron and IANA timezone using backend config keys', () => {
    render(<EditorHarness initial={makeNode('trigger.schedule', { cron: '0 9 * * *', timezone: 'UTC' })} />)
    fireEvent.change(screen.getByLabelText('Cron expression'), { target: { value: '*/5 * * * *' } })
    fireEvent.change(screen.getByLabelText('Timezone'), { target: { value: 'Asia/Singapore' } })
    expect(config()).toEqual({ cron: '*/5 * * * *', timezone: 'Asia/Singapore' })
    expect(screen.getByTestId('save-state').textContent).toBe('allowed')
  })

  it('edits HTTP method, URL and timeout while preserving untouched fields', () => {
    render(<EditorHarness initial={makeNode('action.http_request', { future: [1, null] })} />)
    fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'POST' } })
    fireEvent.change(screen.getByLabelText('URL'), { target: { value: 'https://example.com/data' } })
    fireEvent.change(screen.getByLabelText('Timeout (seconds)'), { target: { value: '5.5' } })
    expect(config()).toEqual({ method: 'POST', url: 'https://example.com/data', timeout: 5.5, future: [1, null] })
  })

  it('allows incomplete HTTP drafts instead of imposing execution readiness', () => {
    render(<EditorHarness initial={makeNode('action.http_request', { method: 'GET', url: '' })} />)
    expect(screen.getByTestId('save-state').textContent).toBe('allowed')
    fireEvent.change(screen.getByLabelText('Timeout (seconds)'), { target: { value: '0' } })
    expect(config().timeout).toBe(0)
    expect(screen.getByTestId('save-state').textContent).toBe('allowed')
  })

  it('preserves the difference between omitted body and explicit JSON null', () => {
    render(<EditorHarness initial={makeNode('action.http_request', { method: 'POST' })} />)
    expect(config()).not.toHaveProperty('body')
    fireEvent.change(screen.getByLabelText('Request body (JSON)'), { target: { value: 'null' } })
    expect(config()).toHaveProperty('body', null)
    fireEvent.change(screen.getByLabelText('Request body (JSON)'), { target: { value: '' } })
    expect(config()).not.toHaveProperty('body')
  })

  it('omits a POST body for GET but restores its unfinished text and error on return', () => {
    render(<EditorHarness initial={makeNode('action.http_request', { method: 'POST', body: { old: true } })} />)
    fireEvent.change(screen.getByLabelText('Request body (JSON)'), { target: { value: '{broken' } })
    expect(screen.getByTestId('save-state').textContent).toBe('blocked')
    fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'GET' } })
    expect(config()).not.toHaveProperty('body')
    expect(screen.getByTestId('save-state').textContent).toBe('allowed')
    expect(screen.queryByLabelText('Request body (JSON)')).toBeNull()
    fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'POST' } })
    expect((screen.getByLabelText('Request body (JSON)') as HTMLTextAreaElement).value).toBe('{broken')
    expect(screen.getByTestId('save-state').textContent).toBe('blocked')
    expect(config()).not.toHaveProperty('body')
  })

  it('rejects unsafe integers in a JSON body without replacing the last valid value', () => {
    render(<EditorHarness initial={makeNode('action.http_request', { method: 'POST', body: { id: 'original' } })} />)
    const raw = '{"id":9007199254740993}'
    fireEvent.change(screen.getByLabelText('Request body (JSON)'), { target: { value: raw } })
    expect(screen.getByRole('alert').textContent).toContain('safe range')
    expect((screen.getByLabelText('Request body (JSON)') as HTMLTextAreaElement).value).toBe(raw)
    expect(config().body).toEqual({ id: 'original' })
    expect(screen.getByTestId('save-state').textContent).toBe('blocked')
    fireEvent.change(screen.getByLabelText('Request body (JSON)'), { target: { value: '{"id":"9007199254740993"}' } })
    expect(config().body).toEqual({ id: '9007199254740993' })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByTestId('save-state').textContent).toBe('allowed')
  })

  it('restores a valid POST body buffer without overwriting other edited HTTP fields', () => {
    render(<EditorHarness initial={makeNode('action.http_request', { method: 'POST', body: { id: 'original' }, extra: { keep: true } })} />)
    fireEvent.change(screen.getByLabelText('Request body (JSON)'), { target: { value: '{"id":"latest"}' } })
    fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'GET' } })
    fireEvent.change(screen.getByLabelText('URL'), { target: { value: 'https://example.com/updated' } })
    fireEvent.change(screen.getByLabelText('Headers (JSON)'), { target: { value: '{"Accept":"application/json"}' } })
    fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'POST' } })
    expect(config()).toEqual({
      method: 'POST', body: { id: 'latest' }, url: 'https://example.com/updated',
      headers: { Accept: 'application/json' }, extra: { keep: true },
    })
  })

  it('uses ancestor-only Condition sources and preserves existing unreachable references', () => {
    render(<EditorHarness initial={makeNode('logic.condition', { source_node_id: 'previous-node', operator: 'exists' })} />)
    const source = screen.getByLabelText('Source node') as HTMLSelectElement
    expect([...source.options].map((item) => item.value)).toEqual(['', 'previous-node', 'upstream'])
    expect(source.value).toBe('previous-node')
    fireEvent.change(source, { target: { value: 'upstream' } })
    fireEvent.change(screen.getByLabelText('Field path'), { target: { value: 'body.user.name' } })
    expect(config()).toEqual({ source_node_id: 'upstream', field: 'body.user.name', operator: 'exists' })
  })

  it('edits all Condition operators and typed compare values', () => {
    render(<EditorHarness initial={makeNode('logic.condition', { source_node_id: 'upstream', operator: 'equals' })} />)
    expect((screen.getByLabelText('Operator') as HTMLSelectElement).options.length).toBe(8)
    fireEvent.change(screen.getByLabelText('Operator'), { target: { value: 'greater_than' } })
    fireEvent.change(screen.getByLabelText('Compare value (JSON)'), { target: { value: '42' } })
    expect(config()).toEqual({ source_node_id: 'upstream', operator: 'greater_than', value: 42 })
    fireEvent.change(screen.getByLabelText('Compare value (JSON)'), { target: { value: 'false' } })
    expect(config().value).toBe(false)
    fireEvent.change(screen.getByLabelText('Operator'), { target: { value: 'exists' } })
    expect(config()).not.toHaveProperty('value')
    expect(screen.queryByLabelText('Compare value (JSON)')).toBeNull()
    fireEvent.change(screen.getByLabelText('Operator'), { target: { value: 'equals' } })
    expect(config().value).toBe(false)
    expect((screen.getByLabelText('Compare value (JSON)') as HTMLTextAreaElement).value).toBe('false')
  })

  it('retains invalid compare input while exists is selected and revalidates on return', () => {
    render(<EditorHarness initial={makeNode('logic.condition', { source_node_id: 'upstream', operator: 'equals', value: true })} />)
    const invalid = 'unfinished comparison text'
    fireEvent.change(screen.getByLabelText('Compare value (JSON)'), { target: { value: invalid } })
    expect(screen.getByTestId('save-state').textContent).toBe('blocked')
    expect(config().value).toBe(true)
    fireEvent.change(screen.getByLabelText('Operator'), { target: { value: 'exists' } })
    expect(config()).not.toHaveProperty('value')
    expect(screen.getByTestId('save-state').textContent).toBe('allowed')
    fireEvent.change(screen.getByLabelText('Field path'), { target: { value: 'body.updated' } })
    fireEvent.change(screen.getByLabelText('Operator'), { target: { value: 'contains' } })
    expect((screen.getByLabelText('Compare value (JSON)') as HTMLTextAreaElement).value).toBe(invalid)
    expect(screen.getByRole('alert').textContent).toContain('Invalid JSON')
    expect(config()).toEqual({ source_node_id: 'upstream', field: 'body.updated', operator: 'contains' })
    expect(screen.getByTestId('save-state').textContent).toBe('blocked')
  })

  it('preserves invalid Transform input across selection and keeps last valid config', () => {
    render(<EditorHarness initial={makeNode('data.transform', { mapping: { source: { value: 'FlowPilot' } } })} />)
    const invalid = '{"mapping":'
    fireEvent.change(screen.getByLabelText('Mapping configuration (JSON)'), { target: { value: invalid } })
    expect(screen.getByRole('alert').textContent).toContain('Invalid JSON')
    expect(config()).toEqual({ mapping: { source: { value: 'FlowPilot' } } })
    expect(screen.getByTestId('save-state').textContent).toBe('blocked')
    fireEvent.click(screen.getByText('Toggle selection'))
    fireEvent.click(screen.getByText('Toggle selection'))
    expect((screen.getByLabelText('Mapping configuration (JSON)') as HTMLTextAreaElement).value).toBe(invalid)
    fireEvent.change(screen.getByLabelText('Mapping configuration (JSON)'), { target: { value: '{"mapping":{"title":{"value":"Repaired"}}}' } })
    expect(config()).toEqual({ mapping: { title: { value: 'Repaired' } } })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByTestId('save-state').textContent).toBe('allowed')
  })

  it('requires an object for Transform while allowing an empty incomplete object', () => {
    render(<EditorHarness initial={makeNode('data.transform')} />)
    fireEvent.change(screen.getByLabelText('Mapping configuration (JSON)'), { target: { value: '[]' } })
    expect(screen.getByRole('alert').textContent).toContain('JSON object')
    fireEvent.change(screen.getByLabelText('Mapping configuration (JSON)'), { target: { value: '{}' } })
    expect(config()).toEqual({})
    expect(screen.getByTestId('save-state').textContent).toBe('allowed')
  })

  it('edits Webhook URL, source, optional path and headers', () => {
    render(<EditorHarness initial={makeNode('action.webhook', { timeout: 10 })} />)
    fireEvent.change(screen.getByLabelText('URL'), { target: { value: 'https://example.com/notify' } })
    fireEvent.change(screen.getByLabelText('Source node'), { target: { value: 'upstream' } })
    fireEvent.change(screen.getByLabelText('Field path'), { target: { value: 'body.result' } })
    fireEvent.change(screen.getByLabelText('Headers (JSON)'), { target: { value: '{"Accept":"application/json"}' } })
    expect(config()).toEqual({
      timeout: 10, url: 'https://example.com/notify', source_node_id: 'upstream',
      path: 'body.result', headers: { Accept: 'application/json' },
    })
  })

  it.each(['Authorization', 'Cookie', 'Proxy-Authorization', 'X-API-Key', 'AUTHORIZATION', 'x_api_key'])(
    'never commits a forbidden %s header and keeps the rejected text visible', (header) => {
      render(<EditorHarness initial={makeNode('action.http_request', { headers: { Accept: 'application/json' } })} />)
      const text = JSON.stringify({ [header]: 'example-sensitive-value' })
      fireEvent.change(screen.getByLabelText('Headers (JSON)'), { target: { value: text } })
      expect(config().headers).toEqual({ Accept: 'application/json' })
      expect(screen.getByRole('alert')).toBeTruthy()
      expect((screen.getByLabelText('Headers (JSON)') as HTMLTextAreaElement).value).toBe(text)
      expect(screen.getByTestId('save-state').textContent).toBe('blocked')
    },
  )

  it('rejects client-managed, duplicate and non-string headers', () => {
    render(<EditorHarness />)
    for (const text of ['{"Host":"example.com"}', '{"Accept":"a","accept":"b"}', '{"Accept":42}']) {
      fireEvent.change(screen.getByLabelText('Headers (JSON)'), { target: { value: text } })
      expect(screen.getByRole('alert')).toBeTruthy()
      expect(config()).not.toHaveProperty('headers')
    }
    fireEvent.change(screen.getByLabelText('Headers (JSON)'), { target: { value: '{"Accept":"application/json"}' } })
    expect(config().headers).toEqual({ Accept: 'application/json' })
  })

  it('preserves unknown node types and config through a read-only view', () => {
    const onChange = vi.fn()
    const node = makeNode('future.node', { nested: { keep: [1, false, null] } })
    render(<PropertiesPanel node={node} nodes={[node]} edges={[]} metadata={[]} drafts={{}} onDraftChange={vi.fn()} onChange={onChange} onDelete={vi.fn()} />)
    const field = screen.getByLabelText('Configuration (read-only)') as HTMLTextAreaElement
    expect(field.readOnly).toBe(true)
    expect(JSON.parse(field.value)).toEqual(node.data.config)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('does not modify unknown configuration when a future node is renamed', () => {
    const futureConfig: JsonObject = { nested: { keep: [1, false, null] }, future_option: 'unchanged' }
    render(<EditorHarness initial={makeNode('future.node', futureConfig)} />)
    fireEvent.change(screen.getByLabelText('Node name'), { target: { value: 'Renamed future node' } })
    expect(screen.getByTestId('name').textContent).toBe('Renamed future node')
    expect(config()).toEqual(futureConfig)
    expect((screen.getByLabelText('Configuration (read-only)') as HTMLTextAreaElement).readOnly).toBe(true)
  })
})

describe('configuration JSON guards', () => {
  it('rejects nonfinite values and nested recognizable credentials', () => {
    expect(parseConfigJson('{"value":1e999}').error).toContain('finite')
    expect(parseConfigJson('{"mapping":{"secret":{"value":"not-for-storage"}}}').error).toContain('credentials')
    expect(parseConfigJson('{"password":""}').error).toBeNull()
    expect(parseConfigJson('{"password":null}').error).toBeNull()
  })

  it('accepts safe integer boundaries and requires strings beyond them', () => {
    expect(parseConfigJson('{"id":9007199254740991}').error).toBeNull()
    expect(parseConfigJson('{"id":-9007199254740991}').error).toBeNull()
    expect(parseConfigJson('{"id":9007199254740992}').error).toContain('safe range')
    expect(parseConfigJson('{"id":-9007199254740992}').error).toContain('safe range')
    expect(parseConfigJson('{"id":"9007199254740992"}').error).toBeNull()
  })

  it('enforces single-line ASCII headers and their size cap', () => {
    expect(validateHeaders({ Accept: 'first\nsecond' })).toBeTruthy()
    expect(validateHeaders({ Accept: 'non-ascii-\u4e2d' })).toBeTruthy()
    expect(validateHeaders({ Accept: 'x'.repeat(8193) })).toContain('limit')
    expect(validateHeaders({ Accept: '' })).toBeNull()
  })
})
