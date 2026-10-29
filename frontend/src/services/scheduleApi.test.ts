import { describe, expect, it, vi } from 'vitest'
import type { Schedule } from '../types/schedule'
import { getSchedule, setScheduleEnabled } from './scheduleApi'

const id = '50ffca80-6763-45f6-b51a-3ed33f55f2ed'
const schedule: Schedule = { workflow_id: id, enabled: true, cron: '0 9 * * mon', timezone: 'Asia/Singapore', next_run_at: '2026-11-02T01:00:00Z', scheduler_running: true, last_error: null }
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status })

describe('schedule API', () => {
  it('gets authoritative schedule andsends onlyenabledfield onupdate', async () => {
    const disabled = { ...schedule, enabled: false, next_run_at: null }
    const fetchMock = vi.fn().mockResolvedValueOnce(response(schedule)).mockResolvedValueOnce(response(disabled))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getSchedule(id)).resolves.toEqual(schedule)
    await expect(setScheduleEnabled(id, false)).resolves.toEqual(disabled)
    expect(fetchMock.mock.calls[1][0]).toBe(`/api/workflows/${id}/schedule`)
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'PUT', body: '{"enabled":false}' })
  })

  it('preserves globallydisabled backend state despiteenabledmetadata', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ ...schedule, scheduler_running: false, next_run_at: null })))
    await expect(getSchedule(id)).resolves.toMatchObject({ enabled: true, scheduler_running: false, next_run_at: null })
  })

  it('returns readiness errors withsafe nodefocusmetadata', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: { code: 'WORKFLOW_NOT_EXECUTABLE', errors: [
      { code: 'INVALID_SCHEDULE_CRON', message: 'Traceback private-marker', node_id: 'schedule' },
    ] } }, 422)))
    await expect(setScheduleEnabled(id, true)).rejects.toMatchObject({ status: 422, issues: [{ node_id: 'schedule', message: 'Schedule requires a valid five-field Cron expression.' }] })
  })

  it.each([404, 503, 500])('surfaces failedmanagementHTTP%s instead of anoptimisticsuccess', async (status) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ detail: 'Traceback hidden-marker' }, status)))
    await expect(setScheduleEnabled(id, false)).rejects.toMatchObject({ status })
  })

  it.each([
    { ...schedule, workflow_id: 'other' }, { ...schedule, enabled: 'true' },
    { ...schedule, next_run_at: '2026-11-02T01:00:00' }, { ...schedule, scheduler_running: 1 },
  ])('rejects mismatched orinvalidscheduledata', async (body) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(body)))
    await expect(getSchedule(id)).rejects.toThrow('invalid schedule data')
  })

  it('keeps cancellation andtimeout distinct fornon-executionrequests', async () => {
    const timer = new AbortController()
    timer.abort()
    vi.spyOn(AbortSignal, 'timeout').mockReturnValue(timer.signal)
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted')))
    await expect(getSchedule(id)).rejects.toThrow('timed out')
    const caller = new AbortController()
    caller.abort()
    await expect(getSchedule(id, caller.signal)).rejects.toThrow('cancelled')
  })
})
