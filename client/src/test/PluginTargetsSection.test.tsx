import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { PluginTargetsSection } from '../components/plugin-manager/PluginTargetsSection'

const getPluginConfigurations = vi.fn()
const getMonitoringTargets = vi.fn()
const applyPluginConfiguration = vi.fn()

vi.mock('../lib/pluginApi', () => ({
  getPluginConfigurations: (id: number) => getPluginConfigurations(id),
  getMonitoringTargets: () => getMonitoringTargets(),
  applyPluginConfiguration: (...args: unknown[]) => applyPluginConfiguration(...args),
}))

const router = { id: 12, hostname: 'router-01', ip_address: '192.168.130.10' }

describe('PluginTargetsSection', () => {
  beforeEach(() => {
    getPluginConfigurations.mockReset().mockResolvedValue([])
    getMonitoringTargets.mockReset().mockResolvedValue([router])
    applyPluginConfiguration.mockReset()
  })

  it('asks to enable the plugin before it can be applied', async () => {
    render(<PluginTargetsSection pluginId={1} pluginName="check_ping" pluginStatus="Ready" onApplied={() => {}} />)

    expect(await screen.findByText('Enable this plugin to apply it to a device.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Apply to Device/ })).not.toBeInTheDocument()
  })

  it('applies an enabled plugin to the chosen device and refreshes', async () => {
    applyPluginConfiguration.mockResolvedValue({ success: true, configuration_id: 4, status: 'Applied', plugin_status: 'Active' })
    const onApplied = vi.fn()
    render(<PluginTargetsSection pluginId={1} pluginName="check_ping" pluginStatus="Enabled" onApplied={onApplied} />)

    fireEvent.change(await screen.findByLabelText('Device'), { target: { value: '12' } })
    getPluginConfigurations.mockResolvedValue([
      { id: 4, target: router, service_description: 'check_ping', status: 'Applied', configuration_data: null, updated_at: '2026-09-30T00:00:00Z' },
    ])
    fireEvent.click(screen.getByRole('button', { name: /Apply to Device/ }))

    await waitFor(() => expect(onApplied).toHaveBeenCalled())
    expect(applyPluginConfiguration).toHaveBeenCalledWith(1, 12, 'check_ping')
    expect(await screen.findByText('Applied')).toBeInTheDocument()
    expect(screen.getByRole('listitem')).toHaveTextContent('router-01 (192.168.130.10)')
  })

  it('shows the Nagios output when the configuration is rejected', async () => {
    applyPluginConfiguration.mockResolvedValue({
      success: false, configuration_id: 4, status: 'Failed', validation_output: 'Error: bad command',
    })
    render(<PluginTargetsSection pluginId={1} pluginName="check_ping" pluginStatus="Active" onApplied={() => {}} />)

    fireEvent.change(await screen.findByLabelText('Device'), { target: { value: '12' } })
    fireEvent.click(screen.getByRole('button', { name: /Apply to Device/ }))

    expect(await screen.findByText(/Nagios rejected the configuration/)).toBeInTheDocument()
    expect(screen.getByText('Error: bad command')).toBeInTheDocument()
  })

  it('points to network discovery when there are no devices', async () => {
    getMonitoringTargets.mockResolvedValue([])
    render(<PluginTargetsSection pluginId={1} pluginName="check_ping" pluginStatus="Enabled" onApplied={() => {}} />)

    expect(await screen.findByText(/Run a network discovery scan first/)).toBeInTheDocument()
  })
})
