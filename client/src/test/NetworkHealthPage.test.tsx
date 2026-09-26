import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { NetworkHealthPage } from '../pages/NetworkHealthPage'

// MiniSparkline uses recharts (AreaChart / ResponsiveContainer).
// jsdom has no SVG layout engine, so mocking it avoids SVG warnings and
// keeps assertions on visible text intact. Both SparklineMetricCard and
// ActiveConnectionsCard render MiniSparkline, so one mock covers both.
vi.mock('../components/network-health/MiniSparkline', () => ({
  MiniSparkline: () => <div data-testid="mini-sparkline" />,
}))

// CpuUtilizationChart directly imports recharts — mock it.
vi.mock('../components/network-health/CpuUtilizationChart', () => ({
  CpuUtilizationChart: () => <div data-testid="cpu-utilization-chart" />,
}))

// The page reads the signed-in user (to allow rescans) and display settings.
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({ user: null, isLoading: false, hasPermission: () => true }),
}))
vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ savedSettings: { dateTimeFormat: 'DD/MM/YYYY', timeZone: 'UTC+08:00' } }),
}))

// The page loads the summary and trends from the API; serve a fixed
// summary so the device counts come from data rather than defaults.
const HOST_COUNTS = { total: 387, up: 321, down: 60, unreachable: 6, flapping: 0, in_downtime: 0 }
const SUMMARY = {
  hosts: HOST_COUNTS,
  services: { ...HOST_COUNTS, ok: 0, warning: 0, critical: 0, unknown: 0 },
  active_alerts: { total: 0, critical: 0, warning: 0, unknown: 0 },
  last_scan: { completed_at: null, is_running: false },
}
const EMPTY_TRENDS = { ping: { configured: false, rta: [], packet_loss: [] }, ncpa: null }

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    apiGet: (path: string) => {
      if (path.startsWith('/api/system/network-health/summary')) return Promise.resolve(SUMMARY)
      if (path.startsWith('/api/system/network-health/trends')) return Promise.resolve(EMPTY_TRENDS)
      return Promise.resolve(null)
    },
    apiPost: () => Promise.resolve(null),
  }
})

function renderPage() {
  return render(
    <MemoryRouter>
      <NetworkHealthPage />
    </MemoryRouter>,
  )
}

describe('NetworkHealthPage', () => {
  it('renders without crashing', () => {
    renderPage()
  })

  it("shows 'Network Health' heading", () => {
    renderPage()
    expect(screen.getByText('Network Health')).toBeInTheDocument()
  })

  it("shows 'Overview of system performance.' description", () => {
    renderPage()
    expect(screen.getByText('Overview of system performance.')).toBeInTheDocument()
  })

  it("shows 'CICT Network' from NetworkInfoCard", () => {
    renderPage()
    expect(screen.getByText('CICT Network')).toBeInTheDocument()
  })

  it("shows 'Latency' SparklineMetricCard", () => {
    renderPage()
    expect(screen.getByText('Latency')).toBeInTheDocument()
  })

  it("shows 'Bandwidth' SparklineMetricCard", () => {
    renderPage()
    expect(screen.getByText('Bandwidth')).toBeInTheDocument()
  })

  it("shows 'Packets Loss' TrendStatCard", () => {
    renderPage()
    expect(screen.getByText('Packets Loss')).toBeInTheDocument()
  })

  it("shows 'Avg. Response Time' TrendStatCard", () => {
    renderPage()
    expect(screen.getByText('Avg. Response Time')).toBeInTheDocument()
  })

  it("shows 'Online Devices' DeviceCountCard", () => {
    renderPage()
    expect(screen.getByText('Online Devices')).toBeInTheDocument()
  })

  it("shows 'Offline Devices' DeviceCountCard", () => {
    renderPage()
    expect(screen.getByText('Offline Devices')).toBeInTheDocument()
  })

  it('shows online and offline counts from the summary', async () => {
    renderPage()
    // Offline = down (60) + unreachable (6).
    const online = screen.getByText('Online Devices').parentElement!.parentElement!
    const offline = screen.getByText('Offline Devices').parentElement!.parentElement!
    expect(await within(online).findByText('321')).toBeInTheDocument()
    expect(await within(offline).findByText('66')).toBeInTheDocument()
  })

  it("shows 'Network Health Insights' panel heading", () => {
    renderPage()
    expect(screen.getByText('Network Health Insights')).toBeInTheDocument()
  })

  it('shows Host Availability card', () => {
    renderPage()
    expect(screen.getByText('Host Availability')).toBeInTheDocument()
  })

  it('shows Active Connections card', () => {
    renderPage()
    expect(screen.getByText('Active Connections')).toBeInTheDocument()
  })

  it('shows Average Resource card', () => {
    renderPage()
    expect(screen.getByText('Average Resource')).toBeInTheDocument()
  })

  it('shows System Activity card', () => {
    renderPage()
    expect(screen.getByText('System Activity')).toBeInTheDocument()
  })
})
