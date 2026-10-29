import { useEffect, useRef, useState } from 'react'
import { getSchedule, setScheduleEnabled } from '../../services/scheduleApi'
import { ApiError } from '../../services/workflowApi'
import type { Schedule } from '../../types/schedule'
import type { ValidationIssue } from '../../types/workflow'

export interface SchedulePanelProps {
  workflowId: string | null
  hasSchedule: boolean
  dirty: boolean
  refreshKey: number
  onIssues?: (issues: ValidationIssue[]) => void
}

function nextRun(value: string | null): string {
  if (!value) return 'No next run scheduled.'
  const date = new Date(value)
  return Number.isFinite(date.getTime()) ? `${date.toISOString().replace('T', ' ').replace('.000Z', '')} UTC` : 'Unavailable'
}

const errorText = (error: unknown) => error instanceof ApiError ? error.message : 'Schedule request failed. Please refresh and try again.'

export default function SchedulePanel({ workflowId, hasSchedule, dirty, refreshKey, onIssues }: SchedulePanelProps) {
  const [schedule, setSchedule] = useState<Schedule | null>(null)
  const [loading, setLoading] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<{ workflowId: string; message: string } | null>(null)
  const [refreshRequest, setRefreshRequest] = useState(0)
  const activeWorkflow = useRef(workflowId)
  activeWorkflow.current = workflowId
  const epoch = useRef(0)
  const reading = useRef(0)
  const pendingRef = useRef(false)
  const write = useRef<AbortController | null>(null)
  const mounted = useRef(true)
  const refreshAfterWrite = useRef(false)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; write.current?.abort() }
  }, [])

  useEffect(() => {
    epoch.current += 1
    pendingRef.current = false
    refreshAfterWrite.current = false
    write.current?.abort()
    setPending(false)
    setSchedule(null)
    setError(null)
  }, [workflowId])

  useEffect(() => {
    if (!workflowId) { setLoading(false); return }
    // A save can request a refresh while a toggle is still in flight. Read the
    // authoritative state after the write settles, rather than racing its reply.
    if (pendingRef.current) { refreshAfterWrite.current = true; return }
    const id = workflowId
    const request = ++reading.current
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    getSchedule(id, controller.signal).then((value) => {
      if (controller.signal.aborted || request !== reading.current || activeWorkflow.current !== id) return
      if (value.workflow_id !== id) throw new Error('Mismatched schedule response')
      setSchedule(value)
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted && request === reading.current && activeWorkflow.current === id) {
        setError({ workflowId: id, message: errorText(failure) })
      }
    }).finally(() => {
      if (!controller.signal.aborted && request === reading.current && mounted.current) setLoading(false)
    })
    return () => controller.abort()
  }, [workflowId, refreshKey, refreshRequest])

  const current = schedule?.workflow_id === workflowId ? schedule : null
  const visibleError = error?.workflowId === workflowId ? error.message : null

  const toggle = async () => {
    if (!workflowId || !current || pendingRef.current || loading) return
    if (!current.enabled && (dirty || !hasSchedule)) return
    const id = workflowId
    const startedEpoch = epoch.current
    const controller = new AbortController()
    write.current = controller
    pendingRef.current = true
    setPending(true)
    setError(null)
    try {
      const value = await setScheduleEnabled(id, !current.enabled, controller.signal)
      if (!mounted.current || controller.signal.aborted || epoch.current !== startedEpoch || activeWorkflow.current !== id) return
      if (value.workflow_id !== id) throw new Error('Mismatched schedule response')
      // Apply only a confirmed backend result. A queued refresh will subsequently
      // fetch again, accounting for a workflow save that auto-disabled this job.
      setSchedule(value)
      onIssues?.([])
    } catch (failure) {
      if (!mounted.current || controller.signal.aborted || epoch.current !== startedEpoch || activeWorkflow.current !== id) return
      setError({ workflowId: id, message: errorText(failure) })
      if (failure instanceof ApiError) onIssues?.(failure.issues ?? [])
    } finally {
      if (mounted.current && epoch.current === startedEpoch && activeWorkflow.current === id) {
        pendingRef.current = false
        setPending(false)
        if (refreshAfterWrite.current) {
          refreshAfterWrite.current = false
          setRefreshRequest((value) => value + 1)
        }
      }
    }
  }

  return (
    <section className="schedule-panel" aria-labelledby="schedule-panel-title">
      <div className="panel-heading"><h2 id="schedule-panel-title">Schedule Settings</h2><button type="button" className="secondary-button" disabled={!workflowId || loading || pending} onClick={() => setRefreshRequest((value) => value + 1)}>Refresh schedule</button></div>
      <div className="panel-content schedule-content">
        {!workflowId && <p>Save your workflow before managing its schedule.</p>}
        {!hasSchedule && <p>This workflow has no Schedule Trigger. Manual workflows run from the Run Workflow button.</p>}
        {dirty && workflowId && <p className="field-help">Unsaved changes. Save your workflow before enabling a schedule. Values below describe the saved configuration; an existing schedule can still be disabled.</p>}
        {loading && <p role="status">Loading schedule…</p>}
        {visibleError && <p role="alert" className="field-error">{visibleError}</p>}
        {current && <>
          <dl className="schedule-summary">
            <div><dt>Schedule status</dt><dd><span className={`schedule-state ${current.enabled ? 'enabled' : 'disabled'}`}>{current.enabled ? 'Enabled' : 'Disabled'}</span></dd></div>
            <div><dt>Cron expression</dt><dd><code>{current.cron ?? 'Not configured'}</code></dd></div>
            <div><dt>Schedule timezone</dt><dd>{current.timezone ?? 'Not configured'}</dd></div>
            <div><dt>Next run time</dt><dd><time dateTime={current.next_run_at ?? undefined}>{nextRun(current.next_run_at)}</time></dd></div>
          </dl>
          {!current.scheduler_running && <p className="field-help">The backend scheduler is stopped or disabled. An enabled configuration will not dispatch jobs until it starts.</p>}
          {current.last_error && <p className="field-error" role="status">Schedule requires attention: <code>{current.last_error}</code>. Review the saved workflow configuration.</p>}
          {(hasSchedule || current.enabled) && <button type="button" className={current.enabled ? 'secondary-button' : 'primary-button'} disabled={loading || pending || (!current.enabled && (dirty || !hasSchedule))} onClick={() => { void toggle() }}>{pending ? 'Updating schedule…' : current.enabled ? 'Disable Schedule' : 'Enable Schedule'}</button>}
          {pending && <p role="status">Waiting for the backend to confirm the schedule change…</p>}
        </>}
        <p className="field-help">Edit Cron and timezone in the Schedule Trigger Properties panel, then save. Scheduled execution is handled by the backend; the browser does not need to stay open.</p>
      </div>
    </section>
  )
}
