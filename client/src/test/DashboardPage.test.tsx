import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { DashboardPage } from '../pages/DashboardPage'

// Charts render SVG through recharts, which jsdom cannot lay out. Stub the
// leaf chart components; every assertion below is about text, not charts.
vi.mock('../components/dashboard/NetworkChart', () => ({
  NetworkChart: () => <div data-testid="network-chart" />,
}))
vi.mock('../components/dashboard/NetworkStatusOverview', () => ({
  NetworkStatusOverview: ({ up, down }: { up: number; down: number }) => (
    <div data-testid="network-status-overview">{`${up} up / ${down} down`}</div>
  ),
}))
vi.mock('../components/dashboard/ResourceUtilizationSection', () => ({
  ResourceUtilizationSection: () => <h2>Average Resource Utilization</h2>,
}))

vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({
    settings: { dashboardRefreshRate: 0, dateTimeFormat: 'YYYY-MM-DD', timeZone: 'UTC+08:00' },
  }),
}))

const apiGet = vi.fn()
const apiPost = vi.fn()

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    apiGet: (path: string) => apiGet(path),
    apiPost: (path: string, data?: unknown) => apiPost(path, data),
  }
})

// ─── API fixtures (server/app/api/system/dashboard.py response shapes) ──────

function statusResponse(running = true) {
  return {
    nagios: {
      running,
      version: '4.5.0',
      last_status_update: '2026-09-26T10:00:00+00:00',
      active_host_checks: true,
      active_service_checks: true,
    },
  }
}

function summaryResponse(overrides: Record<string, unknown> = {}) {
  return {
    hosts: { total: 8, up: 7, down: 1, unreachable: 0, flapping: 0, in_downtime: 0 },
    services: { total: 20, ok: 17, warning: 2, critical: 1, unknown: 0, flapping: 0, in_downtime: 0 },
    active_alerts: { total: 4, critical: 1, warning: 3, unknown: 0 },
    ping_metrics: { configured: true, avg_rta_ms: 12.5, avg_packet_loss_pct: 0.5, host_count: 7 },
    ncpa_metrics: null,
    ...overrides,
  }
}

const ALERT = {
  type: 'service',
  hostname: 'switch-1',
  service_name: 'snmp-uptime-161',
  state: 'CRITICAL',
  state_type: 'HARD',
  timestamp: 1790416800,
  duration_seconds: 600,
  plugin_output: 'SNMP CRITICAL - timeout',
  in_downtime: false,
  ack: null,
}

const EMPTY_TRENDS = { ping: { configured: true, rta: [], packet_loss: [] }, ncpa: null }

let responses: Record<string, unknown>

function routeApi(path: string) {
  if (path.startsWith('/api/system/discover/status')) return Promise.resolve(null)
  for (const [prefix, body] of Object.entries(responses)) {
    if (path.startsWith(prefix)) {
      return body instanceof Error ? Promise.reject(body) : Promise.resolve(body)
    }
  }
  return Promise.resolve(null)
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <DashboardPage />
    </MemoryRouter>,
  )
}

async function renderLoaded() {
  renderDashboard()
  await waitFor(() => expect(screen.queryByText('Loading…')).not.toBeInTheDocument())
}

// The stat cards are the rounded-3xl tiles; titles like "Total Hosts" can
// also appear in the Service Overview sidebar, so match the tile itself.
function statCard(title: string) {
  const tile = screen
    .getAllByText(title)
    .map((el) => el.closest('.rounded-3xl'))
    .find((el): el is HTMLElement => el instanceof HTMLElement)
  if (!tile) throw new Error(`No stat card titled ${title}`)
  return tile
}

describe('DashboardPage', () => {
  beforeEach(() => {
    responses = {
      '/api/system/dashboard/status': statusResponse(),
      '/api/system/dashboard/summary': summaryResponse(),
      '/api/system/dashboard/alerts': { alerts: [ALERT] },
      '/api/system/network-health/trends': EMPTY_TRENDS,
      '/api/system/network-health/services': { items: [], page: 1, per_page: 100, pages: 1, total: 0 },
    }
    apiGet.mockReset()
    apiPost.mockReset()
    apiGet.mockImplementation(routeApi)
    apiPost.mockResolvedValue({})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders the header with the rescan button', async () => {
    await renderLoaded()
    expect(screen.getByText('CICT Network')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /rescan network/i })).toBeInTheDocument()
    expect(screen.getByText('Auto-refresh: Manual')).toBeInTheDocument()
  })

  it('requests every dashboard endpoint', async () => {
    await renderLoaded()
    const paths = apiGet.mock.calls.map(([path]) => path)
    expect(paths).toEqual(expect.arrayContaining([
      '/api/system/dashboard/status',
      '/api/system/dashboard/summary',
      '/api/system/dashboard/alerts?limit=10',
      '/api/system/network-health/trends?hours=24&buckets=24',
      '/api/system/network-health/services?per_page=100',
    ]))
  })

  it('shows Online when Nagios is running', async () => {
    await renderLoaded()
    expect(screen.getByText('Online')).toBeInTheDocument()
  })

  it('shows Offline when Nagios is not running', async () => {
    responses['/api/system/dashboard/status'] = statusResponse(false)
    await renderLoaded()
    expect(screen.getByText('Offline')).toBeInTheDocument()
  })

  it('fills the stat cards from the summary', async () => {
    await renderLoaded()

    expect(within(statCard('Total Hosts')).getByText('8')).toBeInTheDocument()
    expect(within(statCard('Total Hosts')).getByText('7 online')).toBeInTheDocument()
    expect(within(statCard('Network Latency')).getByText('12.5 ms')).toBeInTheDocument()
    expect(within(statCard('Network Latency')).getByText('0.5% packet loss')).toBeInTheDocument()
    expect(within(statCard('Active Warnings')).getByText('3')).toBeInTheDocument()
    expect(within(statCard('Critical Issues')).getByText('1')).toBeInTheDocument()
    expect(within(statCard('Critical Issues')).getByText('1 hosts down')).toBeInTheDocument()
  })

  it('shows no latency when ping data is missing', async () => {
    responses['/api/system/dashboard/summary'] = summaryResponse({
      ping_metrics: { configured: false, avg_rta_ms: null, avg_packet_loss_pct: null, host_count: 0 },
    })
    await renderLoaded()

    expect(within(statCard('Network Latency')).getByText('—')).toBeInTheDocument()
    expect(within(statCard('Network Latency')).getByText('No data')).toBeInTheDocument()
  })

  it('passes host up/down counts to the status overview', async () => {
    await renderLoaded()
    expect(screen.getByTestId('network-status-overview')).toHaveTextContent('7 up / 1 down')
  })

  it('shows the Network Performance section', async () => {
    await renderLoaded()
    expect(screen.getByText('Network Performance')).toBeInTheDocument()
    expect(screen.getByText('Latency')).toBeInTheDocument()
    expect(screen.getByText('Packet Loss')).toBeInTheDocument()
  })

  it('hides resource utilization without NCPA data', async () => {
    await renderLoaded()
    expect(screen.queryByText('Average Resource Utilization')).not.toBeInTheDocument()
  })

  it('shows resource utilization when NCPA data exists', async () => {
    responses['/api/system/dashboard/summary'] = summaryResponse({
      ncpa_metrics: { ncpa_host_count: 2, total_host_count: 8, avg_cpu_pct: 20, avg_disk_pct: 40, avg_memory_pct: 60 },
    })
    await renderLoaded()
    expect(screen.getByText('Average Resource Utilization')).toBeInTheDocument()
  })

  it('lists active alerts', async () => {
    await renderLoaded()
    expect(screen.getByText('Active Alerts')).toBeInTheDocument()
    expect(screen.getByText('switch-1 / snmp-uptime-161')).toBeInTheDocument()
    expect(screen.getByText('SNMP CRITICAL - timeout')).toBeInTheDocument()
  })

  it('shows an empty state when there are no alerts', async () => {
    responses['/api/system/dashboard/alerts'] = { alerts: [] }
    await renderLoaded()
    expect(screen.getByText('No active alerts')).toBeInTheDocument()
  })

  it('acknowledges an alert with a comment', async () => {
    const user = userEvent.setup()
    await renderLoaded()

    await user.click(screen.getByRole('button', { name: 'Acknowledge' }))
    await user.type(screen.getByPlaceholderText(/investigating/i), 'Looking into it')
    const dialog = screen.getByText('Acknowledge switch-1 / snmp-uptime-161').closest('div')!
    await user.click(within(dialog).getByRole('button', { name: 'Acknowledge' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/system/dashboard/alerts/acknowledge', {
        hostname: 'switch-1',
        service_name: 'snmp-uptime-161',
        comment: 'Looking into it',
      })
    })
  })

  it('shows an error banner when loading fails', async () => {
    responses['/api/system/dashboard/summary'] = new Error('Nagios unreachable')
    renderDashboard()
    expect(await screen.findByText('Nagios unreachable')).toBeInTheDocument()
  })
})
