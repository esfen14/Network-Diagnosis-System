import { render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ServiceOverview } from '../components/dashboard/ServiceOverview'
import type { DashboardStatus, DashboardSummary } from '../types/dashboard'
import type { PluginGroup } from '../types/networkHealth'
import type { ServiceRow } from '../types/service'

const NOW = new Date('2026-09-29T10:00:00Z')

function status(overrides: Partial<DashboardStatus['nagios']> = {}): DashboardStatus {
  return {
    nagios: {
      running: true,
      version: '4.5.9',
      lastStatusUpdate: '2026-09-29T09:59:40+00:00',
      activeHostChecks: true,
      activeServiceChecks: true,
      notificationsEnabled: true,
      flapDetectionEnabled: true,
      ...overrides,
    },
  }
}

function summary(counts: { hosts?: number; services?: number } = { hosts: 9, services: 8 }): DashboardSummary {
  return {
    hosts: { total: counts.hosts ?? 0, up: 2, down: 7, unreachable: 0, flapping: 1, inDowntime: 0 },
    services: { total: counts.services ?? 0, ok: 7, warning: 0, critical: 0, unknown: 1, flapping: 0, inDowntime: 2 },
    activeAlerts: { total: 0, critical: 0, warning: 0, unknown: 0 },
    pingMetrics: { configured: true, avgRtaMs: 1, avgPacketLossPct: 0, hostCount: 2 },
    ncpaMetrics: null,
  }
}

const GROUPS: PluginGroup[] = [
  { displayName: 'SSH', total: 2, ok: 1, warning: 0, critical: 1, unknown: 0, worstState: 'critical' },
  { displayName: 'HTTP', total: 3, ok: 3, warning: 0, critical: 0, unknown: 0, worstState: 'ok' },
]

function renderPanel(props: {
  status?: DashboardStatus | null
  summary?: DashboardSummary | null
  pluginGroups?: PluginGroup[] | null
  problemServices?: ServiceRow[]
} = {}) {
  return render(
    <ServiceOverview
      status={props.status === undefined ? status() : props.status}
      summary={props.summary === undefined ? summary() : props.summary}
      problemServices={props.problemServices ?? []}
      pluginGroups={props.pluginGroups === undefined ? GROUPS : props.pluginGroups}
      isLoading={false}
    />,
  )
}

function badge(label: string) {
  const row = screen.getByText(label).parentElement as HTMLElement
  return within(row).getAllByText(/.*/).at(-1) as HTMLElement
}

describe('ServiceOverview', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] })
    vi.setSystemTime(NOW)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows the Nagios version and how fresh the data is', () => {
    renderPanel()
    expect(badge('Nagios 4.5.9')).toHaveTextContent('Running')
    expect(badge('Data Updated')).toHaveTextContent('Just now')
    expect(badge('Data Updated').className).toContain('emerald')
  })

  it('flags stale and missing data', () => {
    renderPanel({ status: status({ lastStatusUpdate: '2026-09-29T09:55:00+00:00' }) })
    expect(badge('Data Updated').className).toContain('yellow')
  })

  it('shows Never in red before the first poll', () => {
    renderPanel({ status: status({ lastStatusUpdate: null }) })
    expect(badge('Data Updated')).toHaveTextContent('Never')
    expect(badge('Data Updated').className).toContain('red')
  })

  it('shows the Nagios switches, with Off called out', () => {
    renderPanel({ status: status({ notificationsEnabled: false, flapDetectionEnabled: null }) })
    expect(badge('Host Checks')).toHaveTextContent('On')
    expect(badge('Notifications')).toHaveTextContent('Off')
    expect(badge('Notifications').className).toContain('red')
    expect(badge('Flap Detection')).toHaveTextContent('Unknown')
  })

  it('shows unknown, flapping and downtime counts instead of repeating the stat cards', () => {
    renderPanel()
    expect(badge('Unknown Services')).toHaveTextContent('1')
    expect(badge('Flapping Hosts')).toHaveTextContent('1')
    expect(badge('Services in Downtime')).toHaveTextContent('2')
    expect(screen.queryByText('Total Hosts')).not.toBeInTheDocument()
    expect(screen.queryByText('Total Services')).not.toBeInTheDocument()
  })

  it('lists services by type with their worst state', () => {
    renderPanel()
    expect(badge('SSH')).toHaveTextContent('1 Critical')
    expect(badge('HTTP')).toHaveTextContent('3/3 OK')
  })

  it('says Unavailable when the plugin breakdown could not load', () => {
    renderPanel({ pluginGroups: null })
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
  })

  it('shows an honest empty state instead of placeholder numbers', () => {
    renderPanel({ summary: summary({ hosts: 0, services: 0 }) })
    expect(screen.getByText(/waiting for the first nagios poll/i)).toBeInTheDocument()
    expect(screen.queryByText('321 Active')).not.toBeInTheDocument()
    expect(screen.queryByText('Services by Type')).not.toBeInTheDocument()
    // The monitoring-system rows still show, since they don't need hosts.
    expect(screen.getByText('Nagios 4.5.9')).toBeInTheDocument()
  })
})
