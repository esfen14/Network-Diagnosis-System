import { render, screen, fireEvent, waitFor, act, renderHook } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { Header } from '../components/layout/Header'
import { useNcpaDeploymentStatus } from '../hooks/useNcpaDeploymentStatus'

const savedSettings = { notifications: false, maintenanceMode: false }
vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ savedSettings }),
}))

let permissions = ['system.deploy.ncpa']
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({
    user: null,
    isLoading: false,
    hasPermission: (permission: string) => permissions.includes(permission),
  }),
}))

const apiGet = vi.fn()
const apiPost = vi.fn()
vi.mock('../lib/api', () => ({
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string) => apiPost(path),
  errorMessage: (err: unknown, fallback: string) => (err instanceof Error ? err.message : fallback),
}))

const STATUS = '/api/system/deployment/ncpa/status'

function counts(overrides: Record<string, number> = {}) {
  return { pending: 0, running: 0, success: 0, failed: 0, down: 0, incompatible: 0, rejected: 0, skipped: 0, ...overrides }
}

function result(id: number, outcome: string) {
  return { device_id: id, hostname: `host-${id}`, ip_address: `10.0.0.${id}`, outcome, error: null, started_at: null, completed_at: null }
}

function run(overrides: Record<string, unknown> = {}) {
  return {
    id: 8,
    status: 'Running',
    progress: 20,
    message: 'Deploying NCPA (2 of 4).',
    error: null,
    start_at: '2026-10-04T10:00:00+00:00',
    completed_at: null,
    started_by: 'Admin User',
    counts: counts({ success: 1, running: 1, pending: 2 }),
    reviewed_at: null,
    reviewed_by: null,
    needs_review: false,
    devices: [result(1, 'Success'), result(2, 'Running'), result(3, 'Pending'), result(4, 'Pending')],
    ...overrides,
  }
}

function Location() {
  const location = useLocation()
  return <p data-testid="location">{location.pathname + location.search}</p>
}

function renderHeader() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Header />
      <Routes>
        <Route path="*" element={<Location />} />
      </Routes>
    </MemoryRouter>,
  )
}

const openPanel = () => fireEvent.click(screen.getByRole('button', { name: 'Notifications' }))

describe('NCPA deployment in the notification panel', () => {
  beforeEach(() => {
    permissions = ['system.deploy.ncpa']
    apiGet.mockReset()
    apiPost.mockReset()
  })

  it('shows progress and stops a running deployment', async () => {
    apiGet.mockResolvedValue(run())
    apiPost.mockResolvedValue({})
    renderHeader()
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith(STATUS))
    openPanel()

    expect(await screen.findByText('NCPA deployment in progress')).toBeInTheDocument()
    expect(screen.getByText(/1 of 4 devices/)).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'NCPA deployment progress' })).toHaveAttribute('aria-valuenow', '20')

    fireEvent.click(screen.getByRole('button', { name: 'Stop' }))
    expect(apiPost).toHaveBeenCalledWith('/api/system/deployment/ncpa/stop')
  })

  it('announces a successful run as ready for review and links to it', async () => {
    apiGet.mockResolvedValue(
      run({
        status: 'Success',
        progress: 100,
        completed_at: '2026-10-04T10:03:00+00:00',
        counts: counts({ success: 2 }),
        devices: [result(1, 'Success'), result(2, 'Success')],
        needs_review: true,
      }),
    )
    renderHeader()
    openPanel()

    expect(await screen.findByText('NCPA deployed: ready for review')).toBeInTheDocument()
    expect(screen.getByText('2 of 2 devices deployed.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Review →' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/ncpa-deployment?tab=history&run=8')
  })

  it('summarises failed and down devices of a partial failure', async () => {
    apiGet.mockResolvedValue(
      run({
        status: 'Partial Failure',
        progress: 100,
        counts: counts({ success: 3, failed: 1, down: 1 }),
        devices: [],
      }),
    )
    renderHeader()
    openPanel()

    expect(await screen.findByText('NCPA deployed with problems')).toBeInTheDocument()
    expect(screen.getByText('3 deployed, 1 failed, 1 down.')).toBeInTheDocument()
  })

  it('does not poll or show the bell without the deploy permission', () => {
    permissions = []
    renderHeader()
    expect(apiGet).not.toHaveBeenCalledWith(STATUS)
    expect(screen.queryByRole('button', { name: 'Notifications' })).not.toBeInTheDocument()
  })
})

describe('useNcpaDeploymentStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    apiGet.mockReset()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('polls fast while running and flags the result when the run finishes', async () => {
    apiGet.mockResolvedValueOnce(run()).mockResolvedValue(run({ status: 'Failed', progress: 100 }))
    const { result } = renderHook(() => useNcpaDeploymentStatus(true))

    await act(async () => {})
    expect(result.current.run?.status).toBe('Running')
    expect(result.current.hasUnseenResult).toBe(false)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(apiGet).toHaveBeenCalledTimes(2)
    expect(result.current.run?.status).toBe('Failed')
    expect(result.current.hasUnseenResult).toBe(true)

    // Once finished it slows down to the idle interval.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(apiGet).toHaveBeenCalledTimes(2)

    act(() => result.current.markSeen())
    expect(result.current.hasUnseenResult).toBe(false)
  })

  it('does nothing when disabled', async () => {
    renderHook(() => useNcpaDeploymentStatus(false))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })
    expect(apiGet).not.toHaveBeenCalled()
  })
})
