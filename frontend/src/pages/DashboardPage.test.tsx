import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../services/workflowApi'
import type { Workflow } from '../types/workflow'
import DashboardPage from './DashboardPage'

const api = vi.hoisted(() => ({ listWorkflows: vi.fn(), deleteWorkflow: vi.fn() }))
vi.mock('../services/workflowApi', async (original) => ({ ...await original<object>(), ...api }))
vi.mock('../services/api', () => ({ getHealth: () => Promise.resolve({ status: 'ok' }) }))

function workflow(type = 'trigger.manual'): Workflow {
  return {
    id: '8a69a715-182d-4ba7-8a5f-d3c59842d4f3', name: 'Morning report', description: 'A saved automation',
    created_at: '2026-10-29T01:00:00Z', updated_at: '2026-10-29T09:15:00+08:00',
    definition: { schema_version: 1, nodes: [{ id: 'start', type, name: 'Start', position: { x: 100, y: 200 }, config: {} }], edges: [] },
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  api.listWorkflows.mockResolvedValue([workflow()])
  api.deleteWorkflow.mockResolvedValue(undefined)
})

describe('workflow dashboard', () => {
  it('loads the existing list and displays supplied fields without extra per-workflow requests', async () => {
    render(<DashboardPage />)
    await screen.findByText('Morning report')
    expect(screen.getByText('A saved automation')).toBeTruthy()
    expect(screen.getByText('Manual')).toBeTruthy()
    expect(screen.getByText('2026-10-29 01:15 UTC')).toBeTruthy()
    expect(api.listWorkflows).toHaveBeenCalledOnce()
    expect(api.listWorkflows).toHaveBeenCalledWith(expect.any(AbortSignal))
    expect(screen.getByText('Schedule and execution status are available in each editor.')).toBeTruthy()
  })

  it('offers create and open navigation into the existing editor', async () => {
    render(<DashboardPage />)
    expect(screen.getByRole('link', { name: 'Create Workflow' }).getAttribute('href')).toBe('/editor')
    const open = await screen.findByRole('link', { name: 'Open Editor for Morning report' })
    expect(open.getAttribute('href')).toBe('/editor?id=8a69a715-182d-4ba7-8a5f-d3c59842d4f3')
  })

  it('shows the empty state without treating it as a failure', async () => {
    api.listWorkflows.mockResolvedValue([])
    render(<DashboardPage />)
    await screen.findByText('No workflows yet.')
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('link', { name: 'Create your first workflow' }).getAttribute('href')).toBe('/editor')
  })

  it('shows backend errors and retries the existing list API', async () => {
    api.listWorkflows.mockRejectedValueOnce(new ApiError(null, 'Cannot reach the backend.')).mockResolvedValueOnce([workflow()])
    render(<DashboardPage />)
    await screen.findByText('Cannot reach the backend.')
    fireEvent.click(screen.getByRole('button', { name: 'Retry workflows' }))
    await screen.findByText('Morning report')
    expect(api.listWorkflows).toHaveBeenCalledTimes(2)
  })

  it('refreshes manually rather than polling', async () => {
    render(<DashboardPage />)
    await screen.findByText('Morning report')
    fireEvent.click(screen.getByRole('button', { name: 'Refresh workflows' }))
    await waitFor(() => expect(api.listWorkflows).toHaveBeenCalledTimes(2))
    expect(screen.queryByText('No workflows yet.')).toBeNull()
  })

  it('requires confirmation before deleting a workflow', async () => {
    render(<DashboardPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Morning report' }))
    const dialog = screen.getByRole('dialog', { name: 'Delete workflow?' })
    expect(within(dialog).getByText(/permanently removes/)).toBeTruthy()
    expect(api.deleteWorkflow).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByText('Morning report')).toBeTruthy()
  })

  it('deletes through the shared API and refreshes after confirmation', async () => {
    api.listWorkflows.mockResolvedValueOnce([workflow()]).mockResolvedValueOnce([])
    render(<DashboardPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Morning report' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete workflow' }))
    await screen.findByText('No workflows yet.')
    expect(api.deleteWorkflow).toHaveBeenCalledWith(workflow().id, expect.any(AbortSignal))
    expect(api.listWorkflows).toHaveBeenCalledTimes(2)
  })

  it('retains the workflow and reports a 409 conflict', async () => {
    api.deleteWorkflow.mockRejectedValue(new ApiError(409, 'This workflow is running. Wait for it to finish before deleting it.'))
    render(<DashboardPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Morning report' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete workflow' }))
    await screen.findByText('This workflow is running. Wait for it to finish before deleting it.')
    expect(screen.getByText('Morning report')).toBeTruthy()
    expect(screen.getByRole('dialog')).toBeTruthy()
  })

  it('prevents repeated delete submissions while the first request is pending', async () => {
    let complete!: () => void
    api.deleteWorkflow.mockReturnValue(new Promise<void>((resolve) => { complete = resolve }))
    api.listWorkflows.mockResolvedValueOnce([workflow()]).mockResolvedValueOnce([])
    render(<DashboardPage />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete Morning report' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete workflow' }))
    const pending = screen.getByRole('button', { name: 'Deleting…' })
    expect(pending.hasAttribute('disabled')).toBe(true)
    fireEvent.click(pending)
    expect(api.deleteWorkflow).toHaveBeenCalledOnce()
    await act(async () => complete())
    await screen.findByText('No workflows yet.')
  })

  it('labels schedule workflows without inventing enabled or execution status', async () => {
    api.listWorkflows.mockResolvedValue([workflow('trigger.schedule')])
    render(<DashboardPage />)
    await screen.findByText('Schedule')
    expect(screen.queryByText('Enabled')).toBeNull()
    expect(screen.queryByText('Success')).toBeNull()
  })

  it('labels unfinished drafts without silently assigning a trigger', async () => {
    const draft = workflow()
    draft.definition.nodes = []
    api.listWorkflows.mockResolvedValue([draft])
    render(<DashboardPage />)
    await screen.findByText('No trigger · Draft')
  })

  it('aborts a pending list when the dashboard unmounts', async () => {
    api.listWorkflows.mockReturnValue(new Promise(() => {}))
    const { unmount } = render(<DashboardPage />)
    await waitFor(() => expect(api.listWorkflows).toHaveBeenCalledOnce())
    const signal = api.listWorkflows.mock.calls[0][0] as AbortSignal
    unmount()
    expect(signal.aborted).toBe(true)
  })
})
