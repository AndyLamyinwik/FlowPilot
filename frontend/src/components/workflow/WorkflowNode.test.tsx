import { render, screen } from '@testing-library/react'
import type { NodeProps } from '@xyflow/react'
import { describe, expect, it, vi } from 'vitest'
import type { FlowNode } from '../../types/workflow'
import WorkflowNode from './WorkflowNode'

vi.mock('@xyflow/react', () => ({
  Position: { Left: 'left', Right: 'right' },
  Handle: ({ id, type, isConnectable, ...props }: { id?: string; type: string; isConnectable: boolean }) => (
    <span data-testid="node-handle" data-handle-id={id ?? 'default'} data-handle-type={type} data-connectable={String(isConnectable)} {...props} />
  ),
}))

function nodeProps(nodeType: string, extra: Partial<FlowNode['data']> = {}): NodeProps<FlowNode> {
  return {
    id: 'node-1', type: 'flowpilotNode', data: { nodeType, name: 'My node', config: {}, ...extra },
    dragging: false, selected: false, isConnectable: true,
    zIndex: 0, draggable: true, selectable: true, deletable: true,
    positionAbsoluteX: 0, positionAbsoluteY: 0,
  }
}

function handles() {
  return screen.getAllByTestId('node-handle').map((element) => [element.dataset.handleType, element.dataset.handleId])
}

describe('generic FlowPilot node', () => {
  it.each(['trigger.manual', 'trigger.schedule'])('does not permit an input on %s', (type) => {
    render(<WorkflowNode {...nodeProps(type)} />)
    expect(handles()).toEqual([['source', 'default']])
  })

  it('gives normal nodes one ordinary input and output', () => {
    render(<WorkflowNode {...nodeProps('action.http_request')} />)
    expect(handles()).toEqual([['target', 'default'], ['source', 'default']])
    expect(screen.getByText('action.http_request')).toBeTruthy()
  })

  it('uses exact true and false source IDs required by the backend', () => {
    render(<WorkflowNode {...nodeProps('logic.condition')} />)
    expect(handles()).toEqual([['target', 'default'], ['source', 'true'], ['source', 'false']])
    expect(screen.getByText('True')).toBeTruthy()
    expect(screen.getByText('False')).toBeTruthy()
  })

  it('renders current user name and backend description safely', () => {
    render(<WorkflowNode {...nodeProps('utility.logger', {
      name: '<script>Custom name</script>',
      metadata: { type: 'utility.logger', display_name: 'Logger', category: 'utility', description: 'Record execution events' },
    })} />)
    expect(screen.getByText('<script>Custom name</script>')).toBeTruthy()
    expect(screen.getByText('Record execution events')).toBeTruthy()
    expect(document.querySelector('script')).toBeNull()
  })

  it('displays unsupported business types instead of dropping the node', () => {
    render(<WorkflowNode {...nodeProps('future.action')} />)
    expect(screen.getByText('future.action')).toBeTruthy()
    expect(screen.getByText(/Configuration is preserved/)).toBeTruthy()
  })

  it('applies a selected state without changing the saved configuration', () => {
    const props = nodeProps('data.transform', { config: { mapping: { title: { value: 'hello' } } } })
    const snapshot = JSON.stringify(props.data)
    render(<WorkflowNode {...props} selected />)
    expect(document.querySelector('.workflow-node.selected')).toBeTruthy()
    expect(JSON.stringify(props.data)).toBe(snapshot)
  })

  it.each(['pending', 'running', 'success', 'failed', 'skipped'])('shows the %s result with text and an execution identity', status => {
    render(<WorkflowNode {...nodeProps('utility.logger', { executionStatus: status, executionId: 'run-123' })} />)
    expect(screen.getByText(status[0].toUpperCase() + status.slice(1))).toBeTruthy()
    expect(document.querySelector(`.execution-node-${status}`)?.getAttribute('data-execution-id')).toBe('run-123')
  })

  it('does not invent a node status when execution has not supplied one', () => {
    render(<WorkflowNode {...nodeProps('utility.logger')} />)
    expect(document.querySelector('.workflow-node-execution')).toBeNull()
  })

  it('falls back safely for a future backend status', () => {
    render(<WorkflowNode {...nodeProps('utility.logger', { executionStatus: 'future_state' })} />)
    expect(screen.getByText('Unknown')).toBeTruthy()
    expect(document.querySelector('.execution-node-unknown')).toBeTruthy()
  })
})
