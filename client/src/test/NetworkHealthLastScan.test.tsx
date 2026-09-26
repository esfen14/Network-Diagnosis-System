import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { NetworkHealthPage } from '../pages/NetworkHealthPage'

vi.mock('../components/network-health/MiniSparkline', () => ({
  MiniSparkline: () => <div data-testid="mini-sparkline" />,
}))
vi.mock('../components/network-health/CpuUtilizationChart', () => ({
  CpuUtilizationChart: () => <div data-testid="cpu-utilization-chart" />,
}))

let permissions: string[] = ['system.discover']
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({
    user: null,
    isLoading: false,
    hasPermission: (permission: string) => permissions.includes(permission),
  }),
}))
vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ savedSettings: { dateTimeFormat: 'YYYY-MM-DD', timeZone: 'UTC+08:00' } }),
}))

const NOW = new Date('2026-09-26T10:00:00Z')
let lastScan: { completed_at: string | null; is_running: boolean }
const apiGet = vi.fn()
const apiPost = vi.fn()

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    apiGet: (path: string) => apiGet(path),
    apiPost: (path: string) => apiPost(path),
  }
})

const EMPTY_TRENDS = { ping: { configured: false, rta: [], packet_loss: [] }, ncpa: null }

function summary() {
  const counts = { total: 0, up: 0, down: 0, unreachable: 0, flapping: 0, in_downtime: 0 }
  return {
    hosts: counts,
    services: { ...counts, ok: 0, warning: 0, critical: 0, unknown: 0 },
    active_alerts: { total: 0, critical: 0, warning: 0, unknown: 0 },
    last_scan: lastScan,
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <NetworkHealthPage />
    </MemoryRouter>,
  )
}

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

describe('NetworkHealthPage last scan', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout', 'Date'] })
    vi.setSystemTime(NOW)
    permissions = ['system.discover']
    lastScan = { completed_at: '2026-09-26T08:00:00+00:00', is_running: false }
    apiGet.mockReset()
    apiPost.mockReset()
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/system/network-health/summary')) return Promise.resolve(summary())
      if (path.startsWith('/api/system/network-health/trends')) return Promise.resolve(EMPTY_TRENDS)
      return Promise.resolve(null)
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the server scan time instead of a placeholder', async () => {
    renderPage()
    await flush()

    expect(screen.getByRole('button', { name: /last scan: 2 hours ago/i })).toBeInTheDocument()
    // 08:00 UTC shown in the UTC+08:00 setting, in the chosen date format.
    expect(screen.getByText('2026-09-26')).toBeInTheDocument()
    expect(screen.getByText('04:00 PM')).toBeInTheDocument()
    expect(screen.queryByText('1 Hour Ago')).not.toBeInTheDocument()
  })

  it('says Never before the first scan', async () => {
    lastScan = { completed_at: null, is_running: false }
    renderPage()
    await flush()

    expect(screen.getByRole('button', { name: /last scan: never/i })).toBeInTheDocument()
  })

  it('shows a scan another user started, and updates when it finishes', async () => {
    lastScan = { completed_at: '2026-09-26T08:00:00+00:00', is_running: true }
    renderPage()
    await flush()

    expect(screen.getByRole('button', { name: /last scan: scanning/i })).toBeDisabled()

    lastScan = { completed_at: '2026-09-26T09:59:00+00:00', is_running: false }
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000)
    })

    expect(screen.getByRole('button', { name: /last scan: 1 min ago/i })).toBeInTheDocument()
  })

  it('runs a real scan and refreshes the time when it succeeds', async () => {
    apiPost.mockResolvedValue({})
    renderPage()
    await flush()

    fireEvent.click(screen.getByRole('button', { name: /last scan/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    await flush()

    expect(apiPost).toHaveBeenCalledWith('/api/system/discover/start')
    expect(screen.getByText('Scanning in Progress')).toBeInTheDocument()

    lastScan = { completed_at: '2026-09-26T10:00:00+00:00', is_running: false }
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/system/discover/status') {
        return Promise.resolve({ status: 'Success', progress: 100, message: 'done', error: null })
      }
      if (path.startsWith('/api/system/network-health/summary')) return Promise.resolve(summary())
      return Promise.resolve(EMPTY_TRENDS)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })

    expect(screen.getByText('Rescan successful!')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /last scan: just now/i })).toBeInTheDocument()
  })

  it('shows the time but blocks rescans without the discover permission', async () => {
    permissions = []
    renderPage()
    await flush()

    expect(screen.getByRole('button', { name: /last scan: 2 hours ago/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /rescan network/i })).toBeDisabled()
  })
})
