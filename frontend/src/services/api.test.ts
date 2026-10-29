import { describe, expect, it, vi } from 'vitest'
import { getHealth } from './api'

describe('health API client', () => {
  it('uses the configured API base URL and removes trailing slashes', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' })))
    vi.stubEnv('VITE_API_BASE_URL', 'https://flowpilot.example/api/')
    vi.stubGlobal('fetch', fetchMock)

    await expect(getHealth()).resolves.toEqual({ status: 'ok' })
    expect(fetchMock.mock.calls[0][0]).toBe('https://flowpilot.example/api/health')
  })

  it('rejects an unsuccessful HTTP response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Unavailable', { status: 503 })))

    await expect(getHealth()).rejects.toThrow('Health request failed (503)')
  })

  it('rejects a response without the expected healthy status', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'unknown' }))))

    await expect(getHealth()).rejects.toThrow('Unexpected health response')
  })
})
