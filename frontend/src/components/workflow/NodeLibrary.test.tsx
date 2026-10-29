import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { NodeTypeMetadata } from '../../types/workflow'
import NodeLibrary from './NodeLibrary'
import { FLOWPILOT_NODE_MIME } from './nodePresentation'

const manual: NodeTypeMetadata = {
  type: 'trigger.manual', display_name: 'Manual Trigger', category: 'trigger', description: 'Start manually',
}
const custom: NodeTypeMetadata = {
  type: 'partner.notification', display_name: 'Partner notification', category: 'partner', description: 'A newly registered node',
}

function setup(overrides: Partial<Parameters<typeof NodeLibrary>[0]> = {}) {
  const onAdd = vi.fn()
  const onRetry = vi.fn()
  render(<NodeLibrary metadata={[manual]} loading={false} error={null} onAdd={onAdd} onRetry={onRetry} {...overrides} />)
  return { onAdd, onRetry }
}

describe('backend driven node library', () => {
  it('shows only the types returned by the backend registry', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Add Manual Trigger' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Add HTTP Request' })).toBeNull()
    expect(screen.getByText('Triggers')).toBeTruthy()
    expect(screen.getByLabelText('1 available node types')).toBeTruthy()
  })

  it('supports newly registered node types without a frontend availability list', () => {
    const { onAdd } = setup({ metadata: [custom] })
    fireEvent.click(screen.getByRole('button', { name: 'Add Partner notification' }))
    expect(onAdd).toHaveBeenCalledWith('partner.notification')
    expect(screen.getByText('A newly registered node')).toBeTruthy()
    expect(screen.getByText('Other')).toBeTruthy()
  })

  it('provides a keyboard accessible click alternative to dragging', () => {
    const { onAdd } = setup()
    const button = screen.getByRole('button', { name: 'Add Manual Trigger' })
    expect(button.getAttribute('type')).toBe('button')
    fireEvent.click(button)
    expect(onAdd).toHaveBeenCalledExactlyOnceWith('trigger.manual')
  })

  it('transfers the backend business node type in the drag payload', () => {
    setup()
    const transfer = { setData: vi.fn(), effectAllowed: '' }
    fireEvent.dragStart(screen.getByRole('button', { name: 'Add Manual Trigger' }), { dataTransfer: transfer })
    expect(transfer.setData).toHaveBeenCalledWith(FLOWPILOT_NODE_MIME, 'trigger.manual')
    expect(transfer.effectAllowed).toBe('copy')
  })

  it('shows backend failures and an actionable retry', () => {
    const { onRetry } = setup({ metadata: [], error: 'Backend is unavailable.' })
    expect(screen.getByRole('alert').textContent).toContain('Backend is unavailable.')
    fireEvent.click(screen.getByRole('button', { name: 'Retry node library' }))
    expect(onRetry).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button', { name: 'Add Manual Trigger' })).toBeNull()
  })

  it('shows a loading state and an empty registry without inventing nodes', () => {
    const view = render(<NodeLibrary metadata={[]} loading error={null} onAdd={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByRole('status').textContent).toContain('Loading')
    view.rerender(<NodeLibrary metadata={[]} loading={false} error={null} onAdd={vi.fn()} onRetry={vi.fn()} />)
    expect(screen.getByText('The backend has no registered node types.')).toBeTruthy()
  })
})
