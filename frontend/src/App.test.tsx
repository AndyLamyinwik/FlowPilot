import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import HomePage from './pages/HomePage'

describe('FlowPilot homepage', () => {
  it('requests the health API on mount and shows a connected backend', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' })))
    vi.stubGlobal('fetch', fetchMock)

    render(<HomePage />)

    expect(screen.getByText('FlowPilot')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Placeholder Dashboard' })).toBeTruthy()
    await screen.findByText('Backend Connected')
    expect(fetchMock).toHaveBeenCalledWith('/api/health', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })

  it('shows a disconnected backend when the network request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    render(<HomePage />)

    await screen.findByText('Backend Disconnected')
  })

  it('aborts the pending request when the page is unmounted', async () => {
    const fetchMock = vi.fn().mockReturnValue(new Promise(() => {}))
    vi.stubGlobal('fetch', fetchMock)

    const { unmount } = render(<HomePage />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce())
    const signal = fetchMock.mock.calls[0][1].signal as AbortSignal
    unmount()

    expect(signal.aborted).toBe(true)
  })
})
