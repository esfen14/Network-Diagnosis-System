import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { PluginsPage } from '../pages/PluginsPage'
import { RunningChecksTable } from '../components/plugin-manager/RunningChecksTable'
import type { RunningChecksResponse } from '../types/plugin'

const runningResponse: RunningChecksResponse = {
  items: [
    {
      id: 4,
      plugin: { id: 2, name: 'check_snmp', display_name: null, status: 'Active' },
      target: { id: 7, hostname: 'core-switch', ip_address: '192.168.130.2' },
      service_description: 'Uptime',
      applied_at: '2026-09-26T09:30:00+00:00',
    },
  ],
  page: 1,
  per_page: 10,
  pages: 1,
  total: 1,
  has_next: false,
  has_prev: false,
}

const emptyList = { items: [], page: 1, per_page: 10, pages: 1, total: 0, has_next: false, has_prev: false }

const getRunningChecks = vi.fn()

vi.mock('../lib/pluginApi', () => ({
  getRunningChecks: (query: unknown) => getRunningChecks(query),
  getPluginInventory: () =>
    Promise.resolve({
      ...emptyList,
      items: [{
        id: 1, name: 'check_ping', display_name: null, category: null, type: 'Nagios',
        source: 'Baseline (ISO)', status: 'Ready', current_version: '2.4.12', updated_at: '2026-09-26T09:00:00+00:00',
      }],
      total: 1,
    }),
  getPluginSummary: () =>
    Promise.resolve({ installed_plugins: 5, active_capabilities: 1, custom_plugins: 0, updates_available: 0, validation_issues: 0 }),
  getPluginScanStatus: () => Promise.resolve(null),
  startPluginScan: () => Promise.resolve(),
}))

// The drawer loads a lot of its own data; stub it to just show which plugin opened.
vi.mock('../components/plugin-manager/PluginDetailsDrawer', () => ({
  PluginDetailsDrawer: ({ pluginId }: { pluginId: number }) => <div>Details for plugin {pluginId}</div>,
}))

describe('RunningChecksTable', () => {
  beforeEach(() => {
    getRunningChecks.mockReset()
  })

  it('lists each running check with its device and service', async () => {
    getRunningChecks.mockResolvedValue(runningResponse)
    render(<RunningChecksTable refreshKey={0} onSelectPlugin={() => {}} />)

    expect(await screen.findByText('check_snmp')).toBeInTheDocument()
    expect(screen.getByText('core-switch')).toBeInTheDocument()
    expect(screen.getByText('192.168.130.2')).toBeInTheDocument()
    expect(screen.getByText('Uptime')).toBeInTheDocument()
    expect(screen.getByText(/1 running check$/)).toBeInTheDocument()
  })

  it('opens the plugin when a row is clicked', async () => {
    getRunningChecks.mockResolvedValue(runningResponse)
    const onSelectPlugin = vi.fn()
    render(<RunningChecksTable refreshKey={0} onSelectPlugin={onSelectPlugin} />)

    fireEvent.click(await screen.findByText('check_snmp'))

    expect(onSelectPlugin).toHaveBeenCalledWith(2)
  })

  it('explains how to start monitoring when nothing is running', async () => {
    getRunningChecks.mockResolvedValue(emptyList)
    render(<RunningChecksTable refreshKey={0} onSelectPlugin={() => {}} />)

    expect(await screen.findByText(/no plugins are running yet/i)).toBeInTheDocument()
  })

  it('reloads when refreshKey changes', async () => {
    getRunningChecks.mockResolvedValue(runningResponse)
    const { rerender } = render(<RunningChecksTable refreshKey={0} onSelectPlugin={() => {}} />)
    await screen.findByText('check_snmp')

    rerender(<RunningChecksTable refreshKey={1} onSelectPlugin={() => {}} />)

    await waitFor(() => expect(getRunningChecks).toHaveBeenCalledTimes(2))
  })
})

describe('PluginsPage tabs', () => {
  beforeEach(() => {
    getRunningChecks.mockReset()
    getRunningChecks.mockResolvedValue(runningResponse)
  })

  it('starts on Currently Running and switches to All Plugins', async () => {
    render(<PluginsPage />)

    const tabs = screen.getAllByRole('tab')
    expect(tabs.map((tab) => tab.textContent?.replace(/\d+/g, '').trim())).toEqual(['Currently Running', 'All Plugins'])

    const runningTab = screen.getByRole('tab', { name: /currently running/i })
    expect(runningTab).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('core-switch')).toBeInTheDocument()
    await waitFor(() => expect(runningTab).toHaveTextContent('1'))

    fireEvent.click(screen.getByRole('tab', { name: /all plugins/i }))

    expect(await screen.findByText('check_ping')).toBeInTheDocument()
    expect(screen.queryByText('core-switch')).not.toBeInTheDocument()
  })

  it('opens plugin details from the running list', async () => {
    render(<PluginsPage />)

    fireEvent.click(await screen.findByText('check_snmp'))

    expect(screen.getByText('Details for plugin 2')).toBeInTheDocument()
  })
})
