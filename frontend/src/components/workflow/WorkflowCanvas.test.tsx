import type { ReactNode } from 'react'
import { createEvent, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import WorkflowCanvas from './WorkflowCanvas'
import { FLOWPILOT_NODE_MIME } from './nodePresentation'

const mocks = vi.hoisted(() => ({
  convert: vi.fn((point: { x: number; y: number }) => ({ x: (point.x - 100) / 2, y: (point.y - 50) / 2 })),
  flowProps: {} as Record<string, unknown>,
}))

vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children, ...props }: { children: ReactNode }) => {
    mocks.flowProps = props
    return <div data-testid="react-flow">{children}</div>
  },
  useReactFlow: () => ({ screenToFlowPosition: mocks.convert }),
  Background: () => <div data-testid="background" />,
  BackgroundVariant: { Dots: 'dots' },
  Controls: () => <div data-testid="controls" />,
  MiniMap: () => <div data-testid="minimap" />,
  Handle: () => null,
  Position: { Left: 'left', Right: 'right' },
}))

function setup(overrides: Partial<Parameters<typeof WorkflowCanvas>[0]> = {}) {
  const props = {
    nodes: [], edges: [], onNodesChange: vi.fn(), onEdgesChange: vi.fn(),
    onConnect: vi.fn(), isValidConnection: vi.fn(), onSelectionChange: vi.fn(),
    onDropNode: vi.fn(), onInit: vi.fn(), ...overrides,
  }
  render(<WorkflowCanvas {...props} />)
  return props
}

describe('controlled workflow canvas', () => {
  it('includes native React Flow navigation controls, minimap and grid', () => {
    const props = setup()
    expect(screen.getByTestId('background')).toBeTruthy()
    expect(screen.getByTestId('controls')).toBeTruthy()
    expect(screen.getByTestId('minimap')).toBeTruthy()
    expect(mocks.flowProps).toMatchObject({
      nodes: props.nodes, edges: props.edges, onNodesChange: props.onNodesChange,
      onEdgesChange: props.onEdgesChange, onConnect: props.onConnect,
      isValidConnection: props.isValidConnection, onSelectionChange: props.onSelectionChange,
      colorMode: 'dark', fitView: false, deleteKeyCode: ['Backspace', 'Delete'],
    })
  })

  it('converts browser drop coordinates through React Flow for a zoomed/panned canvas', () => {
    const { onDropNode } = setup()
    const drop = createEvent.drop(screen.getByRole('region', { name: 'Workflow canvas' }), {
      dataTransfer: { getData: (mime: string) => mime === FLOWPILOT_NODE_MIME ? 'action.http_request' : '' },
    })
    Object.defineProperties(drop, { clientX: { value: 500 }, clientY: { value: 250 } })
    fireEvent(screen.getByRole('region', { name: 'Workflow canvas' }), drop)
    expect(mocks.convert).toHaveBeenCalledWith({ x: 500, y: 250 })
    expect(onDropNode).toHaveBeenCalledExactlyOnceWith('action.http_request', { x: 200, y: 100 })
  })

  it('ignores external drag payloads that are not FlowPilot nodes', () => {
    const { onDropNode } = setup()
    fireEvent.drop(screen.getByRole('region', { name: 'Workflow canvas' }), {
      dataTransfer: { getData: () => '' },
    })
    expect(onDropNode).not.toHaveBeenCalled()
  })

  it('allows a library copy drag onto the canvas', () => {
    setup()
    const transfer = { types: [FLOWPILOT_NODE_MIME], dropEffect: '' }
    const event = createEvent.dragOver(screen.getByRole('region', { name: 'Workflow canvas' }), { dataTransfer: transfer })
    fireEvent(screen.getByRole('region', { name: 'Workflow canvas' }), event)
    expect(event.defaultPrevented).toBe(true)
    expect(transfer.dropEffect).toBe('copy')
  })

  it('keeps the node type registry stable between renders', () => {
    const props = setup()
    const first = mocks.flowProps.nodeTypes
    // Mounting another canvas still refers to the same module-level component map.
    render(<WorkflowCanvas {...props} />)
    expect(mocks.flowProps.nodeTypes).toBe(first)
  })
})
