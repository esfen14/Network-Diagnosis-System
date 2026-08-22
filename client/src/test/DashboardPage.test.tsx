import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { DashboardPage } from '../pages/DashboardPage'

// Mock the chart components that render SVG/recharts to avoid jsdom SVG warnings.
// jsdom has no SVG layout engine, so recharts' SVG elements (defs, linearGradient,
// stop) produce "unrecognized tag" warnings. Mocking the leaf chart components
// prevents those warnings while keeping all visible text assertions intact.
vi.mock('../components/dashboard/NetworkChart', () => ({
  NetworkChart: () => <div data-testid="network-chart" />,
}))

vi.mock('../components/dashboard/ResourceUtilizationSection', () => ({
  ResourceUtilizationSection: () => (
    <div>
      <h2>Average Resource Utilization</h2>
      <p>CPU Usage</p>
    </div>
  ),
}))

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <DashboardPage />
    </MemoryRouter>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.spyOn(global, 'fetch').mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders without crashing', () => {
    renderDashboard()
  })

  it('shows CICT Network heading', () => {
    renderDashboard()
    expect(screen.getByText('CICT Network')).toBeInTheDocument()
  })

  it('shows Online status', () => {
    renderDashboard()
    expect(screen.getByText('Online')).toBeInTheDocument()
  })

  it('shows Total Devices stat card', () => {
    renderDashboard()
    expect(screen.getByText('Total Devices')).toBeInTheDocument()
    expect(screen.getByText('387')).toBeInTheDocument()
  })

  it('shows Network Latency stat card', () => {
    renderDashboard()
    expect(screen.getByText('Network Latency')).toBeInTheDocument()
    expect(screen.getByText('Good')).toBeInTheDocument()
  })

  it('shows Active Warnings stat card', () => {
    renderDashboard()
    expect(screen.getByText('Active Warnings')).toBeInTheDocument()
    expect(screen.getByText('6')).toBeInTheDocument()
  })

  it('shows Critical Issues stat card', () => {
    renderDashboard()
    expect(screen.getByText('Critical Issues')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('shows Network Performance section', () => {
    renderDashboard()
    expect(screen.getByText('Network Performance')).toBeInTheDocument()
  })

  it('shows metric cards for Latency, Packets Loss, Bandwidth', () => {
    renderDashboard()
    expect(screen.getByText('Latency')).toBeInTheDocument()
    expect(screen.getByText('Packets Loss')).toBeInTheDocument()
    expect(screen.getByText('Bandwidth')).toBeInTheDocument()
  })

  it('shows Average Resource Utilization section', () => {
    renderDashboard()
    expect(screen.getByText('Average Resource Utilization')).toBeInTheDocument()
  })

  it('shows Alerts sidebar with alert items', () => {
    renderDashboard()
    expect(screen.getByText('Alerts')).toBeInTheDocument()
    expect(screen.getByText('Alert 1')).toBeInTheDocument()
    expect(screen.getByText('Alert 2')).toBeInTheDocument()
  })
})
