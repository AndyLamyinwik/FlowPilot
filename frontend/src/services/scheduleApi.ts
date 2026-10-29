import type { Schedule } from '../types/schedule'
import { requestJSON } from './workflowApi'

function assertSchedule(value: unknown): asserts value is Schedule {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new Error('Invalid schedule.')
  const item = value as Record<string, unknown>
  const nullableText = (input: unknown) => input === null || typeof input === 'string'
  if (typeof item.workflow_id !== 'string' || typeof item.enabled !== 'boolean'
    || !nullableText(item.cron) || !nullableText(item.timezone) || !nullableText(item.last_error)
    || typeof item.scheduler_running !== 'boolean'
    || !(item.next_run_at === null || (typeof item.next_run_at === 'string'
      && /(?:Z|[+-]\d{2}:\d{2})$/i.test(item.next_run_at) && Number.isFinite(Date.parse(item.next_run_at))))) throw new Error('Invalid schedule data.')
}

function checkForWorkflow(workflowId: string): (value: unknown) => asserts value is Schedule {
  return (value): asserts value is Schedule => {
    assertSchedule(value)
    if (value.workflow_id !== workflowId) throw new Error('Schedule workflow mismatch.')
  }
}

export function getSchedule(workflowId: string, signal?: AbortSignal): Promise<Schedule> {
  return requestJSON(`/workflows/${encodeURIComponent(workflowId)}/schedule`, {}, checkForWorkflow(workflowId), signal, { resource: 'schedule' })
}

export function setScheduleEnabled(workflowId: string, enabled: boolean, signal?: AbortSignal): Promise<Schedule> {
  return requestJSON(`/workflows/${encodeURIComponent(workflowId)}/schedule`, { method: 'PUT', body: JSON.stringify({ enabled }) }, checkForWorkflow(workflowId), signal, { resource: 'schedule' })
}
