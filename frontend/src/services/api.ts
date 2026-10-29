import type { HealthResponse } from '../types/api'

export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/+$/, '')
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const baseUrl = getApiBaseUrl()
  const timeoutSignal = AbortSignal.timeout(5_000)
  const response = await fetch(`${baseUrl}/health`, {
    headers: { Accept: 'application/json' },
    signal: signal ? AbortSignal.any([signal, timeoutSignal]) : timeoutSignal,
  })

  if (!response.ok) {
    throw new Error(`Health request failed (${response.status})`)
  }

  const data: unknown = await response.json()
  if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
    throw new Error('Unexpected health response')
  }

  return { status: 'ok' }
}
