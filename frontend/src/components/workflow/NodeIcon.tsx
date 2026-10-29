export default function NodeIcon({ type, className = '' }: { type: string; className?: string }) {
  let shape
  switch (type) {
    case 'trigger.manual':
      shape = <path d="m9 5 11 7-11 7V5Z" />
      break
    case 'trigger.schedule':
      shape = <><rect x="4" y="5" width="16" height="16" rx="3" /><path d="M8 3v4m8-4v4M4 10h16m-9 3v3h3" /></>
      break
    case 'action.http_request':
      shape = <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z" /></>
      break
    case 'action.webhook':
      shape = <><path d="M13 5h6v6m0-6L9 15m-1-8H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" /></>
      break
    case 'logic.condition':
      shape = <><path d="M6 4v13a3 3 0 1 0 3 3m-3-8h8a4 4 0 0 0 4-4V5m-3 3 3-3 3 3" /><circle cx="6" cy="4" r="2" /></>
      break
    case 'data.transform':
      shape = <><path d="M8 4H5v16h3m8-16h3v16h-3M9 12h6m-3-3 3 3-3 3" /></>
      break
    case 'utility.logger':
      shape = <><rect x="4" y="3" width="16" height="18" rx="3" /><path d="M8 8h8m-8 4h8m-8 4h5" /></>
      break
    default:
      shape = <><rect x="4" y="4" width="16" height="16" rx="4" /><path d="M8 12h8m-4-4v8" /></>
  }
  return (
    <svg className={`node-icon ${className}`} aria-hidden="true" viewBox="0 0 24 24" fill="none"
      width="20" height="20" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      {shape}
    </svg>
  )
}
