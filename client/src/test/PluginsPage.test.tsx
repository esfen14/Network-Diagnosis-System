import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { PluginsPage } from '../pages/PluginsPage'
import { monitoringLabel } from '../components/plugin-manager/PluginInventoryTable'
import type { PluginListItem } from '../types/plugin'

function plugin(overrides: Partial<PluginListItem> = {}): PluginListItem {
  return {
    id: 1, name: 'check_ssh', display_name: null, description: 'Checks SSH.', category: null, type: 'Nagios',
    source: 'Baseline (ISO)', status: 'Ready', current_version: '2.4.12', updated_at: '2026-09-26T09:00:00+00:00',
    service_driven: true, monitoring_usage: { services: 0, devices: 0 },
    ...overrides,
  }
}

const emptyList = { items: [], page: 1, per_page: 10, pages: 1, total: 0, has_next: false, has_prev: false }

const api = vi.hoisted(() => ({
  getPluginInventory: vi.fn(),
  getPluginSummary: vi.fn(),
  getPluginScanStatus: vi.fn(),
  startPluginScan: vi.fn(),
}))

vi.mock('../lib/pluginApi', () => api)

// The drawer loads a lot of its own data; stub it to just show which plugin opened.
vi.mock('../components/plugin-manager/PluginDetailsDrawer', () => ({
  PluginDetailsDrawer: ({ pluginId }: { pluginId: number }) => <div>Details for plugin {pluginId}</div>,
}))

const summary = (overrides = {}) => ({
  installed_plugins: 5, active_capabilities: 1, enabled_plugins: 1, custom_plugins: 0,
  updates_available: 0, validation_issues: 0, ...overrides,
})

describe('PluginsPage', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getPluginSummary.mockResolvedValue(summary())
    api.getPluginScanStatus.mockResolvedValue(null)
    api.getPluginInventory.mockResolvedValue({
      ...emptyList,
      items: [
        plugin({ id: 1, name: 'check_ssh', status: 'Active', monitoring_usage: { services: 12, devices: 5 } }),
        plugin({ id: 2, name: 'check_ping', service_driven: false }),
        plugin({ id: 3, name: 'check_http', status: 'Enabled' }),
        plugin({ id: 4, name: 'check_snmp', status: 'Ready' }),
        plugin({ id: 5, name: 'check_dns', status: 'Active', monitoring_usage: { services: 1, devices: 1 } }),
      ],
      total: 5,
    })
  })

  it('is one plugin inventory with no Currently Running tab', async () => {
    render(<PluginsPage />)

    expect(await screen.findByText('check_ssh')).toBeInTheDocument()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    expect(screen.queryByText(/currently running/i)).not.toBeInTheDocument()
    expect(screen.getByText('Plugin Inventory')).toBeInTheDocument()
  })

  it('shows how much each plugin covers in a Monitoring column', async () => {
    render(<PluginsPage />)

    const row = (name: string) => screen.getByText(name).closest('tr')!
    await screen.findByText('check_ssh')

    expect(screen.getByRole('columnheader', { name: 'Monitoring' })).toBeInTheDocument()
    expect(within(row('check_ssh')).getByText('12 services on 5 devices')).toBeInTheDocument()
    expect(within(row('check_dns')).getByText('1 service on 1 device')).toBeInTheDocument()
    expect(within(row('check_ping')).getByText('Not service-driven')).toBeInTheDocument()
    expect(within(row('check_http')).getByText('No matching services yet')).toBeInTheDocument()
    expect(within(row('check_snmp')).getByText('—')).toBeInTheDocument()
  })

  it('warns that nothing is monitored while no plugin is enabled', async () => {
    api.getPluginSummary.mockResolvedValue(summary({ enabled_plugins: 0, active_capabilities: 0 }))
    render(<PluginsPage />)

    expect(await screen.findByText(/No plugins enabled, so no network services are monitored/)).toBeInTheDocument()
  })

  it('shows no warning once a plugin is enabled', async () => {
    render(<PluginsPage />)

    await screen.findByText('check_ssh')
    expect(screen.queryByText(/No plugins enabled/)).not.toBeInTheDocument()
  })

  it('does not flash the warning before the summary has loaded', async () => {
    api.getPluginSummary.mockReturnValue(new Promise(() => {}))
    render(<PluginsPage />)

    await screen.findByText('check_ssh')
    expect(screen.queryByText(/No plugins enabled/)).not.toBeInTheDocument()
  })

  it('opens the plugin details from a row', async () => {
    render(<PluginsPage />)

    fireEvent.click(await screen.findByText('check_ssh'))

    expect(screen.getByText('Details for plugin 1')).toBeInTheDocument()
  })

  it('shows an error when the inventory cannot be loaded', async () => {
    api.getPluginInventory.mockRejectedValue(new Error('Server unavailable'))
    render(<PluginsPage />)

    expect(await screen.findByText('Server unavailable')).toBeInTheDocument()
  })
})

describe('monitoringLabel', () => {
  it.each([
    [plugin({ service_driven: false }), 'Not service-driven'],
    [plugin({ monitoring_usage: { services: 1, devices: 1 } }), '1 service on 1 device'],
    [plugin({ monitoring_usage: { services: 3, devices: 2 } }), '3 services on 2 devices'],
    [plugin({ status: 'Enabled' }), 'No matching services yet'],
    [plugin({ status: 'Active' }), 'No matching services yet'],
    [plugin({ status: 'Disabled' }), '—'],
    [plugin({ status: 'Ready' }), '—'],
  ])('describes %#', (item, expected) => {
    expect(monitoringLabel(item)).toBe(expected)
  })
})
