import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ExecutionDetail, ExecutionResult, NodeExecutionResult } from '../../types/execution'
import ExecutionPanel from './ExecutionPanel'
import ExecutionStatus from './ExecutionStatus'
import ValidationPanel from './ValidationPanel'

const started = '2026-10-29T09:00:00Z'
const finished = '2026-10-29T09:00:01.250Z'
function node(node_id: string, status = 'success'): NodeExecutionResult {
  return { node_id, status, started_at: started, finished_at: finished, duration_ms: 1250, output: null, error: null }
}
function result(overrides: Partial<ExecutionResult> = {}): ExecutionResult {
  return { execution_id: 'run-1', workflow_id: 'workflow-1', status: 'success', started_at: started, finished_at: finished,
    error: null, node_results: [node('b', 'skipped'), node('a')], ...overrides }
}
function historical(overrides: Partial<ExecutionDetail> = {}): ExecutionDetail {
  return { ...result(), trigger_type: 'schedule', duration_ms: 1250, created_at: started,
    definition_hash: 'abc', outputs_stored: false, history_truncated: false, ...overrides }
}

describe('execution display', () => {
  it.each(['pending', 'running', 'success', 'failed', 'skipped', 'interrupted'])('gives %s a text and icon status', status => {
    const { container } = render(<ExecutionStatus status={status} />)
    expect(container.querySelector(`.status-${status}`)).toBeTruthy()
    expect(screen.getByText(status[0].toUpperCase() + status.slice(1))).toBeTruthy()
    expect(container.querySelector('[aria-hidden="true"]')?.textContent).toBeTruthy()
  })

  it.each(['future_state', '__proto__', 'constructor'])('uses a safe fallback for %s', status => {
    const { container } = render(<ExecutionStatus status={status} />)
    expect(screen.getByText('Unknown')).toBeTruthy()
    expect(container.querySelector('.status-unknown')).toBeTruthy()
  })

  it('shows the actual failed execution independently of HTTP success', () => {
    render(<ExecutionPanel execution={result({ status: 'failed', error: { code: 'HTTP_TIMEOUT', message: 'Traceback secret', node_id: 'a' } })} workflowName="Workflow" />)
    expect(screen.getByRole('region', { name: 'Execution result' })).toBeTruthy()
    expect(screen.getByText('HTTP request timed out.')).toBeTruthy()
    expect(screen.queryByText(/Traceback secret/)).toBeNull()
    expect(screen.getByText('Nodes: 2 · Success: 1 · Failed: 0 · Skipped: 1')).toBeTruthy()
    expect(screen.getAllByText('Failed')).toHaveLength(1)
  })

  it('matches selected node details using ID even with duplicate names and reversed result order', () => {
    const select = vi.fn()
    const output = result({ node_results: [{ ...node('b'), output: { marker: 'node-b' } }, { ...node('a'), output: { marker: 'node-a' } }] })
    render(<ExecutionPanel execution={output} workflowName="Workflow" selectedNodeId="a" nodeNames={{ a: 'Same name', b: 'Same name' }} onSelectNode={select} />)
    const detail = screen.getByRole('region', { name: 'Node execution details' })
    expect(within(detail).getByText('a')).toBeTruthy()
    expect(within(detail).getByLabelText('Node output').textContent).toContain('node-a')
    fireEvent.click(screen.getAllByRole('button', { name: /Same name/ })[0])
    expect(select).toHaveBeenCalledWith('b')
  })

  it('shows UTC, derived duration and execution metadata without inventing output', () => {
    render(<ExecutionPanel execution={result()} workflowName="Workflow" triggerType="manual" />)
    expect(screen.getByText('run-1')).toBeTruthy()
    expect(screen.getByText('workflow-1')).toBeTruthy()
    expect(screen.getByText('Manual')).toBeTruthy()
    expect(screen.getAllByText(/2026-10-29.*UTC/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('1.25 s').length).toBeGreaterThan(0)
    expect(screen.getByText('Output not stored or unavailable.')).toBeTruthy()
  })

  it('redacts common sensitive fields before rendering without modifying the result', () => {
    const execution = result({ node_results: [{ ...node('a'), output: { title: 'Safe', Authorization: 'Bearer hidden', nested: { cookie: 'private', api_key: 'key' } } }] })
    const original = structuredClone(execution)
    render(<ExecutionPanel execution={execution} workflowName="Workflow" />)
    const output = screen.getByLabelText('Node output').textContent!
    expect(output).toContain('Safe')
    expect(output).not.toContain('Bearer hidden')
    expect(output).not.toContain('private')
    expect(output).not.toContain('"key"')
    expect(execution).toEqual(original)
  })

  it('bounds large JSON output and safely displays arbitrary text as text', () => {
    render(<ExecutionPanel execution={result({ node_results: [{ ...node('a'), output: { value: '<script>unsafe()</script>', large: 'x'.repeat(100_000) } }] })} workflowName="Workflow" />)
    expect(screen.getByLabelText('Node output').textContent!.length).toBeLessThan(40_000)
    expect(document.querySelector('script')).toBeNull()
  })

  it('keeps historical output separate and does not use current node names or invoke selection', () => {
    const select = vi.fn()
    render(<ExecutionPanel execution={historical({ history_truncated: true })} workflowName="Saved Workflow" historical nodeNames={{ a: 'Current node', b: 'Current node' }} onSelectNode={select} />)
    expect(screen.getByText(/may use a different workflow version/)).toBeTruthy()
    expect(screen.getByText(/limited in size/)).toBeTruthy()
    expect(screen.queryByText('Current node')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /a.*Success/ }))
    expect(select).not.toHaveBeenCalled()
    expect(screen.getByText('Schedule')).toBeTruthy()
  })

  it('shows an empty result state rather than fabricating nodes', () => {
    render(<ExecutionPanel execution={result({ node_results: [] })} workflowName="Workflow" />)
    expect(screen.getByText('No node results available.')).toBeTruthy()
  })
})

describe('workflow validation display', () => {
  it('distinguishes graph validation from final executor readiness', () => {
    render(<ValidationPanel report={{ can_save: true, structural: { valid: true, errors: [], warnings: [] }, execution_readiness: { valid: true, errors: [], warnings: [] } }} onSelectNode={vi.fn()} />)
    expect(screen.getByText('Validation Passed')).toBeTruthy()
    expect(screen.getByText(/Execute API performs the final readiness check/)).toBeTruthy()
  })

  it('displays errors and warnings with node location actions and no raw traceback', () => {
    const select = vi.fn()
    render(<ValidationPanel report={{ can_save: true, structural: { valid: true, errors: [], warnings: [] }, execution_readiness: { valid: false, errors: [{ code: 'MISSING_TRIGGER', message: 'Traceback internal secret' }], warnings: [{ code: 'DISCONNECTED_NODE', message: 'Raw warning', node_id: 'node-1' }] } }} issues={[{ code: 'INVALID_NODE_CONFIG', message: 'token=secret', node_id: 'node-2' }]} onSelectNode={select} />)
    expect(screen.getByText('Validation Failed')).toBeTruthy()
    expect(screen.getByText('Errors')).toBeTruthy()
    expect(screen.getByText('Warnings')).toBeTruthy()
    expect(screen.queryByText(/Traceback internal/)).toBeNull()
    expect(screen.queryByText(/token=secret/)).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Locate node node-2' }))
    expect(select).toHaveBeenCalledWith('node-2')
  })
})
