import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { DiscoverySettings } from '../components/settings/DiscoverySettings'
import { ApiError } from '../lib/api'

const getDiscoverySettings = vi.fn()
const saveDiscoverySettings = vi.fn()

vi.mock('../lib/discoverySettingsApi', () => ({
  getDiscoverySettings: () => getDiscoverySettings(),
  saveDiscoverySettings: (...args: unknown[]) => saveDiscoverySettings(...args),
}))

const values = {
  networks: ['192.168.130.0/24'],
  tcpPorts: ['1-6000'],
  udpPorts: [53, 161],
  tcpServiceOverrides: { '22': 'ssh' },
  udpServiceOverrides: { '161': 'snmp' },
  tcpForcedServices: { '5693': 'ncpa' },
  udpForcedServices: {},
}

function loaded(overrides: Record<string, unknown> = {}) {
  return {
    settings: { ...values, version: 0, updatedAt: null },
    defaults: values,
    scanRunning: false,
    ...overrides,
  }
}

describe('DiscoverySettings', () => {
  beforeEach(() => {
    getDiscoverySettings.mockReset().mockResolvedValue(loaded())
    saveDiscoverySettings.mockReset()
  })

  it('shows the current networks, ports and overrides', async () => {
    render(<DiscoverySettings />)

    expect(await screen.findByText('192.168.130.0/24')).toBeInTheDocument()
    expect(screen.getByText('1-6000')).toBeInTheDocument()
    expect(screen.getByLabelText('Remove 161')).toBeInTheDocument()
    expect(screen.getByText('ssh')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save Changes/ })).toBeDisabled()
  })

  it('adds a network and saves with the loaded version', async () => {
    saveDiscoverySettings.mockImplementation((next, version) =>
      Promise.resolve({ ...next, version: version + 1, updatedAt: '2026-09-30T00:00:00Z' }))
    render(<DiscoverySettings />)

    fireEvent.change(await screen.findByLabelText('Add Networks'), { target: { value: '10.0.5.0/24' } })
    fireEvent.click(screen.getByLabelText('Add to Networks'))
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/ }))

    await waitFor(() => expect(saveDiscoverySettings).toHaveBeenCalled())
    const [sent, version] = saveDiscoverySettings.mock.calls[0]
    expect(sent.networks).toEqual(['192.168.130.0/24', '10.0.5.0/24'])
    expect(version).toBe(0)
  })

  it('rejects an invalid port before saving', async () => {
    render(<DiscoverySettings />)

    fireEvent.change(await screen.findByLabelText('Add TCP Ports'), { target: { value: '80 --script' } })
    fireEvent.click(screen.getByLabelText('Add to TCP Ports'))

    expect(screen.getAllByText(/Enter a port \(1-65535\)/)[0]).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save Changes/ })).toBeDisabled()
  })

  it('adds a service override and parses numeric ports', async () => {
    saveDiscoverySettings.mockImplementation((next, version) =>
      Promise.resolve({ ...next, version: version + 1, updatedAt: null }))
    render(<DiscoverySettings />)

    fireEvent.change(await screen.findByLabelText('TCP port'), { target: { value: '5666' } })
    fireEvent.change(screen.getByLabelText('TCP service name'), { target: { value: 'nrpe' } })
    fireEvent.click(screen.getByLabelText('Add TCP override'))
    fireEvent.change(screen.getByLabelText('Add UDP Ports'), { target: { value: '123' } })
    fireEvent.click(screen.getByLabelText('Add to UDP Ports'))
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/ }))

    await waitFor(() => expect(saveDiscoverySettings).toHaveBeenCalled())
    const [sent] = saveDiscoverySettings.mock.calls[0]
    expect(sent.tcpServiceOverrides).toEqual({ '22': 'ssh', '5666': 'nrpe' })
    expect(sent.tcpForcedServices).toEqual({ '5693': 'ncpa' })
    expect(sent.udpPorts).toEqual([53, 161, 123])
  })

  it('edits the always-treat-port-as rules separately from the fallback names', async () => {
    saveDiscoverySettings.mockImplementation((next, version) =>
      Promise.resolve({ ...next, version: version + 1, updatedAt: null }))
    render(<DiscoverySettings />)

    expect(await screen.findByText('Always Treat Port As')).toBeInTheDocument()
    expect(screen.getByText('Fallback Service Names')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('UDP always port'), { target: { value: '1161' } })
    fireEvent.change(screen.getByLabelText('UDP always service name'), { target: { value: 'snmp' } })
    fireEvent.click(screen.getByLabelText('Add UDP always override'))
    fireEvent.click(screen.getByLabelText('Remove TCP always override for port 5693'))
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/ }))

    await waitFor(() => expect(saveDiscoverySettings).toHaveBeenCalled())
    const [sent] = saveDiscoverySettings.mock.calls[0]
    expect(sent.udpForcedServices).toEqual({ '1161': 'snmp' })
    expect(sent.tcpForcedServices).toEqual({})
    expect(sent.udpServiceOverrides).toEqual({ '161': 'snmp' })
  })

  it('shows the server message when a save is rejected', async () => {
    saveDiscoverySettings.mockRejectedValue(new ApiError("'10.0.0.0/8' is too large.", 400))
    render(<DiscoverySettings />)

    fireEvent.click(await screen.findByLabelText('Remove 53'))
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/ }))

    expect(await screen.findByText("'10.0.0.0/8' is too large.")).toBeInTheDocument()
  })

  it('blocks saving while a scan is running', async () => {
    getDiscoverySettings.mockResolvedValue(loaded({ scanRunning: true }))
    render(<DiscoverySettings />)

    expect(await screen.findByText(/scan is running/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Remove 53'))
    expect(screen.getByRole('button', { name: /Save Changes/ })).toBeDisabled()
  })
})
