import { render, screen } from '@testing-library/react'
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

  it('shows 321 online count and 66 offline count', () => {
    renderPage()
    expect(screen.getByText('321')).toBeInTheDocument()
    expect(screen.getByText('66')).toBeInTheDocument()
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
