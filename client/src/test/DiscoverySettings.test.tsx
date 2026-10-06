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
  tcpPortServices: { '22': 'ssh', '5666': 'nrpe', '5693': 'ncpa' },
  udpPortServices: { '161': 'snmp', '5666': 'nrpe' },
}

const derived = {
  ncpaPort: 5693,
  resolution: {
    tcp: {
      '22': { plugin: 'check_ssh', kind: 'plugin' },
      '5666': { plugin: 'check_tcp', kind: 'generic' },
      '5693': { plugin: 'check_ncpa', kind: 'plugin' },
    },
    udp: {
      '161': { plugin: 'check_snmp', kind: 'plugin' },
      '5666': { plugin: null, kind: 'skipped' },
    },
  },
}

function loaded(overrides: Record<string, unknown> = {}) {
  return {
    settings: { ...values, ...derived, version: 0, updatedAt: null },
    defaults: { ...values, ...derived },
    scanRunning: false,
    ...overrides,
  }
}

describe('DiscoverySettings', () => {
  beforeEach(() => {
    getDiscoverySettings.mockReset().mockResolvedValue(loaded())
    saveDiscoverySettings.mockReset()
  })

  it('shows the current networks, ports and expected services', async () => {
    render(<DiscoverySettings />)

    expect(await screen.findByText('192.168.130.0/24')).toBeInTheDocument()
    expect(screen.getByText('1-6000')).toBeInTheDocument()
    expect(screen.getByLabelText('Remove 161')).toBeInTheDocument()
    expect(screen.getByText('ssh')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save Changes/ })).toBeDisabled()
  })

  it('has one Port to Service section instead of two separate tables', async () => {
    render(<DiscoverySettings />)

    expect(await screen.findByText('Port → Service')).toBeInTheDocument()
    expect(screen.queryByText('Always Treat Port As')).not.toBeInTheDocument()
    expect(screen.queryByText('Fallback Service Names')).not.toBeInTheDocument()
    expect(screen.getByText(/not relabelled/)).toBeInTheDocument()
  })

  it('shows which check each entry leads to and warns about generic and skipped ones', async () => {
    render(<DiscoverySettings />)

    expect(await screen.findByText('check_ssh')).toBeInTheDocument()
    expect(screen.getByText('check_tcp (generic TCP check)')).toBeInTheDocument()
    expect(screen.getByText('Skipped (no UDP check for this service)')).toBeInTheDocument()
  })

  it('shows NCPA\'s port as fixed with no remove button', async () => {
    render(<DiscoverySettings />)

    await screen.findByText('Port → Service')
    expect(screen.getByText('Fixed')).toBeInTheDocument()
    expect(screen.queryByLabelText('Remove TCP service for port 5693')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Remove TCP service for port 22')).toBeInTheDocument()
  })

  it('refuses to map the NCPA port to another service', async () => {
    render(<DiscoverySettings />)

    fireEvent.change(await screen.findByLabelText('TCP port'), { target: { value: '5693' } })
    fireEvent.change(screen.getByLabelText('TCP service name'), { target: { value: 'http' } })
    fireEvent.click(screen.getByLabelText('Add TCP service'))

    expect(screen.getByText(/NCPA's port and always maps to ncpa/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save Changes/ })).toBeDisabled()
  })

  it('says a new entry is checked after it is saved', async () => {
    render(<DiscoverySettings />)

    fireEvent.change(await screen.findByLabelText('TCP port'), { target: { value: '3306' } })
    fireEvent.change(screen.getByLabelText('TCP service name'), { target: { value: 'mysql' } })
    fireEvent.click(screen.getByLabelText('Add TCP service'))

    expect(screen.getByText('Known after saving')).toBeInTheDocument()
  })

  it('adds a network and saves with the loaded version', async () => {
    saveDiscoverySettings.mockImplementation((next, version) =>
      Promise.resolve({ ...next, ...derived, version: version + 1, updatedAt: '2026-09-30T00:00:00Z' }))
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

  it('adds and removes expected services and parses numeric ports', async () => {
    saveDiscoverySettings.mockImplementation((next, version) =>
      Promise.resolve({ ...next, ...derived, version: version + 1, updatedAt: null }))
    render(<DiscoverySettings />)

    fireEvent.change(await screen.findByLabelText('TCP port'), { target: { value: '3306' } })
    fireEvent.change(screen.getByLabelText('TCP service name'), { target: { value: 'mysql' } })
    fireEvent.click(screen.getByLabelText('Add TCP service'))
    fireEvent.click(screen.getByLabelText('Remove UDP service for port 5666'))
    fireEvent.change(screen.getByLabelText('Add UDP Ports'), { target: { value: '123' } })
    fireEvent.click(screen.getByLabelText('Add to UDP Ports'))
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/ }))

    await waitFor(() => expect(saveDiscoverySettings).toHaveBeenCalled())
    const [sent] = saveDiscoverySettings.mock.calls[0]
    expect(sent.tcpPortServices).toEqual({ '22': 'ssh', '3306': 'mysql', '5666': 'nrpe', '5693': 'ncpa' })
    expect(sent.udpPortServices).toEqual({ '161': 'snmp' })
    expect(sent.udpPorts).toEqual([53, 161, 123])
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
