import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../services/workflowApi'
import type { Schedule } from '../../types/schedule'
import SchedulePanel from './SchedulePanel'

const api = vi.hoisted(() => ({ getSchedule: vi.fn(), setScheduleEnabled: vi.fn() }))
vi.mock('../../services/scheduleApi', () => api)
const ID = '8a69a715-182d-4ba7-8a5f-d3c59842d4f3'
const OTHER = '55ac7618-9891-46c4-ad98-54173aa52960'
const state = (overrides: Partial<Schedule> = {}): Schedule => ({
  workflow_id: ID, enabled: false, cron: '*/5 * * * *', timezone: 'Asia/Singapore',
  next_run_at: null, scheduler_running: true, last_error: null, ...overrides,
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail })
  return { promise, resolve, reject }
}

beforeEach(() => {
  vi.resetAllMocks()
  api.getSchedule.mockResolvedValue(state())
  api.setScheduleEnabled.mockImplementation(async (_id: string, enabled: boolean) => state({ enabled, next_run_at: enabled ? '2026-10-29T09:05:00Z' : null }))
})

function setup(overrides: Partial<Parameters<typeof SchedulePanel>[0]> = {}) {
  const props = { workflowId: ID, hasSchedule: true, dirty: false, refreshKey: 0, ...overrides }
  const view = render(<SchedulePanel {...props} />)
  return { ...view, props }
}

describe('saved schedule management', () => {
  it('loads the actual backend state and labels timezone explicitly', async () => {
    api.getSchedule.mockResolvedValue(state({ enabled: true, next_run_at: '2026-10-29T17:05:00+08:00' }))
    setup()
    await screen.findByText('Enabled')
    expect(screen.getByText('*/5 * * * *')).toBeTruthy()
    expect(screen.getByText('Asia/Singapore')).toBeTruthy()
    expect(screen.getByText('2026-10-29 09:05:00 UTC')).toBeTruthy()
    expect(api.getSchedule).toHaveBeenCalledWith(ID, expect.any(AbortSignal))
  })

  it('requires a saved workflow before issuing any schedule request', async () => {
    setup({ workflowId: null })
    expect(screen.getByText('Save your workflow before managing its schedule.')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Enable Schedule' })).toBeNull()
    expect(api.getSchedule).not.toHaveBeenCalled()
  })

  it('does not present an Enable control for manual workflows', async () => {
    api.getSchedule.mockResolvedValue(state({ cron: null, timezone: null }))
    setup({ hasSchedule: false })
    await screen.findByText('Disabled')
    expect(screen.getByText(/This workflow has no Schedule Trigger/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Enable Schedule' })).toBeNull()
  })

  it('keeps enable disabled for unsaved changes', async () => {
    setup({ dirty: true })
    const button = await screen.findByRole('button', { name: 'Enable Schedule' })
    expect(button.hasAttribute('disabled')).toBe(true)
    fireEvent.click(button)
    expect(api.setScheduleEnabled).not.toHaveBeenCalled()
    expect(screen.getByText(/Values below describe the saved configuration/)).toBeTruthy()
  })

  it('waits for confirmation and prevents duplicate writes', async () => {
    const response = deferred<Schedule>()
    api.setScheduleEnabled.mockReturnValue(response.promise)
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Enable Schedule' }))
    expect(screen.getByText('Disabled')).toBeTruthy()
    const pending = screen.getByRole('button', { name: 'Updating schedule…' })
    expect(pending.hasAttribute('disabled')).toBe(true)
    fireEvent.click(pending)
    expect(api.setScheduleEnabled).toHaveBeenCalledTimes(1)
    await act(async () => response.resolve(state({ enabled: true, next_run_at: '2026-10-29T09:05:00Z' })))
    expect(screen.getByText('Enabled')).toBeTruthy()
    expect(screen.getByText('2026-10-29 09:05:00 UTC')).toBeTruthy()
  })

  it('disables an enabled schedule and clears next run after backend confirmation', async () => {
    api.getSchedule.mockResolvedValue(state({ enabled: true, next_run_at: '2026-10-29T09:05:00Z' }))
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Disable Schedule' }))
    await screen.findByText('Disabled')
    expect(screen.getByText('No next run scheduled.')).toBeTruthy()
    expect(api.setScheduleEnabled).toHaveBeenCalledWith(ID, false, expect.any(AbortSignal))
  })

  it('can disable the saved job even when an unsaved draft removes its trigger', async () => {
    api.getSchedule.mockResolvedValue(state({ enabled: true }))
    setup({ dirty: true, hasSchedule: false })
    fireEvent.click(await screen.findByRole('button', { name: 'Disable Schedule' }))
    await screen.findByText('Disabled')
    expect(api.setScheduleEnabled).toHaveBeenCalledWith(ID, false, expect.any(AbortSignal))
    expect(screen.queryByRole('button', { name: 'Enable Schedule' })).toBeNull()
  })

  it('retains Disabled and passes readiness issues back when enable is rejected', async () => {
    const issue = { code: 'INVALID_SCHEDULE_CRON', message: 'Schedule cron must be valid', node_id: 'schedule' }
    api.setScheduleEnabled.mockRejectedValue(new ApiError(422, 'Invalid schedule configuration.', [issue]))
    const onIssues = vi.fn()
    setup({ onIssues })
    fireEvent.click(await screen.findByRole('button', { name: 'Enable Schedule' }))
    await screen.findByRole('alert')
    expect(screen.getByText('Disabled')).toBeTruthy()
    expect(screen.getByText('Invalid schedule configuration.')).toBeTruthy()
    expect(onIssues).toHaveBeenCalledWith([issue])
  })

  it('retains Enabled and next run when disabling fails', async () => {
    api.getSchedule.mockResolvedValue(state({ enabled: true, next_run_at: '2026-10-29T09:05:00Z' }))
    api.setScheduleEnabled.mockRejectedValue(new ApiError(null, 'Cannot reach the backend.'))
    setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Disable Schedule' }))
    await screen.findByText('Cannot reach the backend.')
    expect(screen.getByText('Enabled')).toBeTruthy()
    expect(screen.getByText('2026-10-29 09:05:00 UTC')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Disable Schedule' }).hasAttribute('disabled')).toBe(false)
  })

  it('distinguishes enabled metadata from a globally disabled scheduler', async () => {
    api.getSchedule.mockResolvedValue(state({ enabled: true, scheduler_running: false }))
    setup()
    await screen.findByText('Enabled')
    expect(screen.getByText(/The backend scheduler is stopped or disabled/)).toBeTruthy()
    expect(screen.getByText('No next run scheduled.')).toBeTruthy()
  })

  it('reloads authoritative state after saving instead of assuming the schedule stayed enabled', async () => {
    api.getSchedule.mockResolvedValueOnce(state({ enabled: true })).mockResolvedValueOnce(state({ last_error: 'SCHEDULE_INVALID_WORKFLOW' }))
    const { rerender, props } = setup()
    await screen.findByText('Enabled')
    rerender(<SchedulePanel {...props} refreshKey={1} />)
    await screen.findByText('Disabled')
    expect(screen.getByText('SCHEDULE_INVALID_WORKFLOW')).toBeTruthy()
  })

  it('shows a load error and supports explicit refresh without polling', async () => {
    api.getSchedule.mockRejectedValueOnce(new ApiError(404, 'Workflow not found.')).mockResolvedValueOnce(state())
    setup()
    await screen.findByText('Workflow not found.')
    fireEvent.click(screen.getByRole('button', { name: 'Refresh schedule' }))
    await screen.findByText('Disabled')
    expect(api.getSchedule).toHaveBeenCalledTimes(2)
  })

  it('ignores a late read response from the previously opened workflow', async () => {
    const old = deferred<Schedule>()
    api.getSchedule.mockReturnValueOnce(old.promise).mockResolvedValueOnce(state({ workflow_id: OTHER, cron: '0 9 * * mon' }))
    const { rerender, props } = setup()
    const firstSignal = api.getSchedule.mock.calls[0][1] as AbortSignal
    rerender(<SchedulePanel {...props} workflowId={OTHER} />)
    await screen.findByText('0 9 * * mon')
    await act(async () => old.resolve(state({ enabled: true })))
    expect(firstSignal.aborted).toBe(true)
    expect(screen.queryByText('Enabled')).toBeNull()
    expect(screen.getByText('0 9 * * mon')).toBeTruthy()
  })

  it('ignores a late toggle response after workflow switching', async () => {
    const old = deferred<Schedule>()
    api.setScheduleEnabled.mockReturnValue(old.promise)
    api.getSchedule.mockResolvedValueOnce(state()).mockResolvedValueOnce(state({ workflow_id: OTHER, cron: '0 9 * * mon' }))
    const { rerender, props } = setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Enable Schedule' }))
    const firstSignal = api.setScheduleEnabled.mock.calls[0][2] as AbortSignal
    rerender(<SchedulePanel {...props} workflowId={OTHER} />)
    await screen.findByText('0 9 * * mon')
    await act(async () => old.resolve(state({ enabled: true })))
    expect(firstSignal.aborted).toBe(true)
    expect(screen.queryByText('Enabled')).toBeNull()
  })

  it('defers a save-triggered refresh until the in-flight toggle settles', async () => {
    const response = deferred<Schedule>()
    api.setScheduleEnabled.mockReturnValue(response.promise)
    api.getSchedule.mockResolvedValueOnce(state()).mockResolvedValueOnce(state({ enabled: false, last_error: 'SCHEDULE_INVALID_WORKFLOW' }))
    const { rerender, props } = setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Enable Schedule' }))
    rerender(<SchedulePanel {...props} refreshKey={1} />)
    expect(api.getSchedule).toHaveBeenCalledTimes(1)
    await act(async () => response.resolve(state({ enabled: true })))
    await screen.findByText('SCHEDULE_INVALID_WORKFLOW')
    expect(screen.getByText('Disabled')).toBeTruthy()
    expect(api.getSchedule).toHaveBeenCalledTimes(2)
  })

  it('aborts active schedule requests on unmount', async () => {
    api.getSchedule.mockReturnValue(new Promise(() => {}))
    const { unmount } = setup()
    await waitFor(() => expect(api.getSchedule).toHaveBeenCalledOnce())
    const signal = api.getSchedule.mock.calls[0][1] as AbortSignal
    unmount()
    expect(signal.aborted).toBe(true)
  })
})
