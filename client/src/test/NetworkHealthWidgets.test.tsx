import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { NetworkHealthPage } from '../pages/NetworkHealthPage'

// Covers the cards backed by network_health_activity.py: host availability,
// system activity, CPU utilization, active connections and insights.

vi.mock('../components/network-health/MiniSparkline', () => ({
  MiniSparkline: () => <div data-testid="mini-sparkline" />,
}))
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({ user: null, isLoading: false, hasPermission: () => true }),
}))
vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ savedSettings: { dateTimeFormat: 'YYYY-MM-DD', timeZone: 'UTC+00:00' } }),
}))

const apiGet = vi.fn()
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return { ...actual, apiGet: (path: string) => apiGet(path), apiPost: () => Promise.resolve(null) }
})

const COUNTS = { total: 2, up: 2, down: 0, unreachable: 0, flapping: 0, in_downtime: 0 }
const RESPONSES: Record<string, unknown> = {
  '/api/system/network-health/summary': {
    hosts: COUNTS,
    services: { ...COUNTS, ok: 0, warning: 0, critical: 0, unknown: 0 },
    active_alerts: { total: 0, critical: 0, warning: 0, unknown: 0 },
    last_scan: { completed_at: null, is_running: false },
  },
  '/api/system/network-health/trends': { ping: { configured: false, rta: [], packet_loss: [] }, ncpa: null },
  '/api/system/network-health/plugins': { groups: [{ display_name: 'PROCS', total: 1, ok: 1, warning: 0, critical: 0, unknown: 0, worst_state: 'ok' }] },
  '/api/system/network-health/availability': {
    days: 7,
    availability_pct: 97.25,
    change_pct: -1.5,
    trend_pct: 2.25,
    daily: [
      { start: '2026-09-22T10:00:00+00:00', end: '2026-09-23T10:00:00+00:00', availability_pct: 95 },
      { start: '2026-09-23T10:00:00+00:00', end: '2026-09-24T10:00:00+00:00', availability_pct: null },
    ],
  },
  '/api/system/network-health/system-activity': {
    processes: { device_count: 2, total: 300, avg_per_device: 150, state: 'warning', peak_24h: { hostname: 'localhost', count: 210 } },
    users: { device_count: 2, total: 5, min_per_device: 2, max_per_device: 3, change_1h: 3 },
  },
  '/api/system/network-health/connections': {
    available: true, hostname: 'localhost', established: 1234, listening: 12, time_wait: 7, other: 3, total: 1256,
  },
  '/api/system/network-health/insights': {
    insights: [
      { severity: 'critical', message: '1 device is down or unreachable.', at: new Date().toISOString() },
      { severity: 'info', message: 'Average latency across online devices is 2.0 ms.', at: null },
    ],
  },
  '/api/system/network-health/plugin-trends': {
    hours: 24,
    plugins: [
      {
        plugin_name: 'check_dig', display_name: 'DNS Lookup (dig)',
        total: 2, ok: 1, warning: 1, critical: 0, unknown: 0, worst_state: 'warning',
        metrics: [
          {
            metric: 'time', unit: 's', averaged: true, service_count: 2, current_avg: 0.3,
            current: [
              { hostname: 'db', service: 'DNS Lookup', value: 0.4 },
              { hostname: 'web', service: 'DNS Lookup', value: 0.2 },
            ],
            points: [{ bucket_start: '2026-09-29T09:00:00+00:00', avg_value: 0.3, unit: 's' }],
          },
          {
            metric: 'size', unit: 'B', averaged: false, service_count: 1, current_avg: null,
            current: [{ hostname: 'web', service: 'DNS Lookup', value: 512 }],
            points: [],
          },
        ],
      },
    ],
  },
  '/api/system/network-health/cpu': {
    hosts: ['localhost', 'web'], hostname: 'localhost', service: 'ncpa-cpu-5693',
    current_pct: 42.5, avg_pct: 30, max_pct: 60, points: [],
  },
}

function respond(path: string) {
  const key = Object.keys(RESPONSES).find((k) => path.startsWith(k))
  return key ? Promise.resolve(RESPONSES[key]) : Promise.resolve(null)
}

async function renderPage() {
  render(
    <MemoryRouter>
      <NetworkHealthPage />
    </MemoryRouter>,
  )
  await act(async () => {})
}

describe('NetworkHealthPage backend-driven cards', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiGet.mockImplementation(respond)
  })

  it('shows host availability from the availability endpoint', async () => {
    await renderPage()
    expect(screen.getByText('97.3 %')).toBeInTheDocument()
    expect(screen.getByText('-1.5%')).toBeInTheDocument()
    expect(screen.getByText('+2.3%')).toBeInTheDocument()
    expect(screen.getByLabelText('Daily availability').children).toHaveLength(2)
  })

  it('shows system activity rows', async () => {
    await renderPage()
    expect(screen.getByText('150/device')).toBeInTheDocument()
    expect(screen.getByText('Warning')).toBeInTheDocument()
    expect(screen.getByText('300 processes')).toBeInTheDocument()
    expect(screen.getByText('210 on localhost')).toBeInTheDocument()
    expect(screen.getByText('2-3/device')).toBeInTheDocument()
    expect(screen.getByText('+3 users')).toBeInTheDocument()
  })

  it('shows established connections with a breakdown', async () => {
    await renderPage()
    expect(screen.getByText('1,234')).toBeInTheDocument()
    expect(screen.getByText('TCP connections on the Nagios server (localhost)')).toBeInTheDocument()
  })

  it('shows generated insights and the monitored checks', async () => {
    await renderPage()
    expect(screen.getByText('1 device is down or unreachable.')).toBeInTheDocument()
    expect(screen.getByText('Average latency across online devices is 2.0 ms.')).toBeInTheDocument()
    expect(screen.getByText('PROCS')).toBeInTheDocument()
  })

  it('shows CPU stats and reloads for the picked host', async () => {
    await renderPage()
    expect(screen.getByText('CPU Utilization for localhost')).toBeInTheDocument()
    expect(screen.getByText('42.5%')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Host'), { target: { value: 'web' } })
    await act(async () => {})
    expect(apiGet).toHaveBeenCalledWith('/api/system/network-health/cpu?hours=24&buckets=24&hostname=web')
  })

  it('keeps the other cards when Nagios availability is unreachable', async () => {
    apiGet.mockImplementation((path: string) =>
      path.startsWith('/api/system/network-health/availability')
        ? Promise.reject(new ApiError('Unable to read availability from Nagios.', 502))
        : respond(path),
    )
    await renderPage()
    expect(screen.getByText('Unable to read availability from Nagios.')).toBeInTheDocument()
    expect(screen.getByText('1,234')).toBeInTheDocument()
  })

  it('gives each added plugin its own card with its averaged value', async () => {
    await renderPage()
    expect(screen.getByText('DNS Lookup (dig)')).toBeInTheDocument()
    expect(screen.getByText('0.300 s')).toBeInTheDocument()
    expect(screen.getByText('avg time across 2 services')).toBeInTheDocument()
    expect(screen.getByText('1 Warning')).toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/api/system/network-health/plugin-trends?hours=24&buckets=24')
  })

  it('opens the graph with per-service values, including ones not averaged', async () => {
    await renderPage()
    fireEvent.click(screen.getByText('DNS Lookup (dig)'))
    expect(screen.getByText('check_dig — average across services')).toBeInTheDocument()
    expect(screen.getByText('Current values per service')).toBeInTheDocument()
    expect(screen.getByText('512 B')).toBeInTheDocument()
    expect(screen.getByText('0.400 s')).toBeInTheDocument()
  })

  it('explains the section when no plugins have been added', async () => {
    RESPONSES['/api/system/network-health/plugin-trends'] = { hours: 24, plugins: [] }
    await renderPage()
    expect(screen.getByText(/no plugins have been added yet/i)).toBeInTheDocument()
  })
})
