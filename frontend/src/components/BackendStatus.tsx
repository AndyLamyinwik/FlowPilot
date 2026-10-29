import { useEffect, useState } from 'react'
import { getHealth } from '../services/api'

type ConnectionState = 'checking' | 'connected' | 'disconnected'

const labels: Record<ConnectionState, string> = {
  checking: 'Checking connection…',
  connected: 'Backend Connected',
  disconnected: 'Backend Disconnected',
}

export default function BackendStatus({ compact = false }: { compact?: boolean }) {
  const [connection, setConnection] = useState<ConnectionState>('checking')

  useEffect(() => {
    const controller = new AbortController()

    getHealth(controller.signal)
      .then(() => {
        if (!controller.signal.aborted) setConnection('connected')
      })
      .catch(() => {
        if (!controller.signal.aborted) setConnection('disconnected')
      })

    return () => controller.abort()
  }, [])

  const dotColor = {
    checking: 'bg-amber-500',
    connected: 'bg-emerald-600',
    disconnected: 'bg-rose-500',
  }[connection]

  if (compact) return <div className={`backend-indicator ${connection}`} role="status" aria-live="polite"><span />{labels[connection]}</div>

  return (
    <section aria-labelledby="connection-title" className="rounded-2xl border border-stone-200 bg-white p-6 sm:p-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold tracking-[0.16em] text-stone-500 uppercase">System overview</p>
          <h2 id="connection-title" className="text-lg font-semibold tracking-tight text-stone-900">Backend Connection Status</h2>
        </div>
        <div role="status" aria-live="polite" className="inline-flex items-center gap-2.5 rounded-full bg-stone-50 px-4 py-2.5 text-sm font-medium text-stone-700">
          <span aria-hidden="true" className={`size-2 rounded-full ${dotColor}`} />
          {labels[connection]}
        </div>
      </div>
      <p className="mt-5 max-w-xl text-sm leading-6 text-stone-500">
        {connection === 'connected'
          ? 'Your workspace is connected to the FlowPilot backend. The foundation is ready.'
          : connection === 'disconnected'
            ? 'The backend could not be reached. Check that it is running and refresh this page to try again.'
            : 'Making a quick health check to your FlowPilot backend.'}
      </p>
    </section>
  )
}
