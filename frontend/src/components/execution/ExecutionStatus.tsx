const statuses = {
  pending: { label: 'Pending', icon: '○' },
  running: { label: 'Running', icon: '◷' },
  success: { label: 'Success', icon: '✓' },
  failed: { label: 'Failed', icon: '✕' },
  skipped: { label: 'Skipped', icon: '↷' },
  interrupted: { label: 'Interrupted', icon: '!' },
} as const

export function statusPresentation(status: string) {
  return Object.hasOwn(statuses, status)
    ? { ...statuses[status as keyof typeof statuses], className: status }
    : { label: 'Unknown', icon: '?', className: 'unknown' }
}

export default function ExecutionStatus({ status }: { status: string }) {
  const state = statusPresentation(status)
  return <span className={`execution-status status-${state.className}`}><span aria-hidden="true">{state.icon}</span>{state.label}</span>
}
