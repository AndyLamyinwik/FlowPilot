import { useEffect, useState } from 'react'
import { getExecution, getExecutionHistory } from '../../services/executionApi'
import type { ExecutionDetail, ExecutionHistoryPage } from '../../types/execution'
import { formatDuration, formatTimestamp } from '../../utils/executionDisplay'
import ExecutionPanel from './ExecutionPanel'
import ExecutionStatus from './ExecutionStatus'

export interface ExecutionHistoryProps {
  workflowId: string | null
  refreshKey: number
  workflowName?: string
}

const PAGE_SIZE = 20
const filters = ['success', 'failed', 'interrupted', 'skipped', 'running']
const message = (error: unknown) => error instanceof Error ? error.message : 'The request could not be completed. Please try again.'

function History({ workflowId, refreshKey, workflowName }: { workflowId: string; refreshKey: number; workflowName: string }) {
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const [page, setPage] = useState<ExecutionHistoryPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ExecutionDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [detailRefresh, setDetailRefresh] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setLoading(true)
    setError(null)
    setPage(null)
    getExecutionHistory(workflowId, { limit: PAGE_SIZE, offset, ...(status ? { status } : {}) }, controller.signal)
      .then(result => {
        if (!active || controller.signal.aborted) return
        if (result.items.some(item => item.workflow_id !== workflowId)) throw new Error('History response does not match this workflow.')
        if (offset > 0 && offset >= result.total) {
          // Retention or deletion can remove the current last page. Re-query
          // the last remaining page instead of showing an inverted range.
          setOffset(Math.floor(Math.max(0, result.total - 1) / PAGE_SIZE) * PAGE_SIZE)
          setSelectedId(null)
          return
        }
        setPage(result)
      }).catch((reason: unknown) => {
        if (active && !controller.signal.aborted) setError(message(reason))
      }).finally(() => { if (active && !controller.signal.aborted) setLoading(false) })
    return () => { active = false; controller.abort() }
  }, [workflowId, status, offset, refresh, refreshKey])

  useEffect(() => {
    setDetail(null)
    setDetailError(null)
    if (!selectedId) { setDetailLoading(false); return }
    const controller = new AbortController()
    let active = true
    setDetailLoading(true)
    getExecution(selectedId, controller.signal).then(result => {
      if (!active || controller.signal.aborted) return
      if (result.workflow_id !== workflowId || result.execution_id !== selectedId) throw new Error('Execution response does not match this workflow.')
      setDetail(result)
    }).catch((reason: unknown) => {
      if (active && !controller.signal.aborted) setDetailError(message(reason))
    }).finally(() => { if (active && !controller.signal.aborted) setDetailLoading(false) })
    return () => { active = false; controller.abort() }
  }, [selectedId, workflowId, detailRefresh])

  const changePage = (nextOffset: number) => { setOffset(nextOffset); setSelectedId(null) }
  return (
    <section className="execution-history" aria-label="Execution history">
      <div className="execution-panel-heading"><h2>Execution History</h2><button className="secondary-button" type="button" disabled={loading} onClick={() => setRefresh(value => value + 1)}>Refresh history</button></div>
      <div className="history-controls"><label htmlFor="history-status">History status</label><select id="history-status" className="field-select" value={status} onChange={event => { setStatus(event.target.value); setOffset(0); setSelectedId(null) }}>
        <option value="">All</option>{filters.map(filter => <option key={filter} value={filter}>{filter[0].toUpperCase() + filter.slice(1)}</option>)}
      </select></div>
      {loading && <p role="status">Loading execution history…</p>}
      {error && <p className="execution-error" role="alert">History load failed. {error}</p>}
      {!loading && !error && page?.items.length === 0 && <p className="execution-empty">No executions yet.</p>}
      {!loading && !error && page && page.items.length > 0 && <div className="history-table-wrap"><table className="history-table">
        <thead><tr><th scope="col">Execution time (UTC)</th><th scope="col">Status</th><th scope="col">Trigger</th><th scope="col">Duration</th><th scope="col">Details</th></tr></thead>
        <tbody>{page.items.map(item => <tr key={item.execution_id}>
          <td>{formatTimestamp(item.started_at)}</td><td><ExecutionStatus status={item.status} /></td><td>{item.trigger_type === 'schedule' ? 'Schedule' : 'Manual'}</td><td>{formatDuration(item.duration_ms)}</td>
          <td><button className="secondary-button" type="button" aria-label={`View details ${item.execution_id}`} onClick={() => setSelectedId(item.execution_id)}>View Details</button></td>
        </tr>)}</tbody>
      </table></div>}
      {!loading && !error && page && <div className="history-pagination"><span>{page.total ? `${offset + 1}–${offset + page.items.length}` : '0'} of {page.total} executions</span>
        <button className="secondary-button" type="button" disabled={offset === 0} onClick={() => changePage(Math.max(0, offset - PAGE_SIZE))}>Previous page</button>
        <button className="secondary-button" type="button" disabled={offset + PAGE_SIZE >= page.total} onClick={() => changePage(offset + PAGE_SIZE)}>Next page</button>
      </div>}
      {selectedId && <div className="history-detail"><div className="execution-panel-heading"><h3>Historical execution</h3><button className="secondary-button" type="button" onClick={() => setSelectedId(null)}>Close details</button></div>
        {detailLoading && <p role="status">Loading execution details…</p>}
        {detailError && <div><p className="execution-error" role="alert">Execution details unavailable. {detailError}</p><button className="secondary-button" type="button" onClick={() => setDetailRefresh(value => value + 1)}>Retry details</button></div>}
        {detail && detail.execution_id === selectedId && detail.workflow_id === workflowId && <ExecutionPanel execution={detail} workflowName={workflowName} historical />}
      </div>}
    </section>
  )
}

export default function ExecutionHistory({ workflowId, refreshKey, workflowName = 'Saved workflow' }: ExecutionHistoryProps) {
  return workflowId
    ? <History key={workflowId} workflowId={workflowId} refreshKey={refreshKey} workflowName={workflowName} />
    : <section className="execution-history" aria-label="Execution history"><h2>Execution History</h2><p className="muted">Save a workflow to view its execution history.</p></section>
}
