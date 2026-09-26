import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  LAST_ACTIVITY_KEY,
  SessionTimeoutWatcher,
} from '../components/layout/SessionTimeoutWatcher'
import { LoginPage } from '../pages/LoginPage'

// 1-minute timeout keeps the timer arithmetic readable.
vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ savedSettings: { sessionTimeout: 1 } }),
}))

const fetchMock = vi.fn()

function mockMeStatus(status: number) {
  fetchMock.mockImplementation((url: string) =>
    Promise.resolve({
      ok: status < 400,
      status,
      json: () => Promise.resolve({}),
      url,
    }),
  )
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Routes>
        <Route
          path="/dashboard"
          element={
            <>
              <SessionTimeoutWatcher />
              <div>Dashboard Page</div>
            </>
          }
        />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

const EXPIRED_NOTICE = /session expired due to inactivity/i

describe('SessionTimeoutWatcher', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    mockMeStatus(200)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('logs out and shows the expired notice after the idle timeout', async () => {
    renderDashboard()

    await advance(75_000)

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/user/logout',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(screen.getByText(EXPIRED_NOTICE)).toBeInTheDocument()
    expect(localStorage.getItem(LAST_ACTIVITY_KEY)).toBeNull()
  })

  it('stays signed in while the user is active', async () => {
    renderDashboard()

    await advance(45_000)
    fireEvent.keyDown(window)
    await advance(45_000)

    expect(screen.getByText('Dashboard Page')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalledWith('/api/user/logout', expect.anything())
  })

  it('stays signed in while activity in another tab is recent', async () => {
    renderDashboard()

    await advance(45_000)
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()))
    await advance(45_000)

    expect(screen.getByText('Dashboard Page')).toBeInTheDocument()
  })

  it('shows the expired notice when the server rejects a leftover session', async () => {
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now() - 3_600_000))
    mockMeStatus(401)

    renderDashboard()
    await advance(0)

    expect(screen.getByText(EXPIRED_NOTICE)).toBeInTheDocument()
  })

  it('redirects to login without the notice when there was no session', async () => {
    mockMeStatus(401)

    renderDashboard()
    await advance(0)

    expect(screen.getByText('Log In to your Account')).toBeInTheDocument()
    expect(screen.queryByText(EXPIRED_NOTICE)).not.toBeInTheDocument()
  })
})
