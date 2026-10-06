import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { StatusDetailDrawer } from '../components/device-inventory/StatusDetailDrawer'

const api = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return { ...actual, apiGet: (path: string) => api.apiGet(path), apiPost: vi.fn(), apiDelete: vi.fn() }
})

const permissions = vi.hoisted(() => ({ granted: new Set<string>() }))
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({ user: null, isLoading: false, hasPermission: (name: string) => permissions.granted.has(name) }),
}))

// The section has its own tests; here it only shows that it was rendered, and for which device.
vi.mock('../components/device-inventory/DevicePortsSection', () => ({
  DevicePortsSection: ({ deviceId, hostname }: { deviceId: number; hostname: string }) => (
    <div>Ports section for device {deviceId} ({hostname})</div>
  ),
}))

function detail(overrides: Record<string, unknown> = {}) {
  return {
    hostname: 'web-01',
    device_id: 4,
    state: 'Up',
    state_type: 'HARD',
    plugin_output: 'PING OK',
    last_check: '2026-10-05T09:30:00+00:00',
    check_latency: 0.012,
    check_execution_time: 0.05,
    is_flapping: false,
    in_downtime: false,
    nagios_ack: 'none',
    ack: null,
    perf_data: [],
    services: [{ service: 'ssh-22-tcp', state: 'Ok', plugin_output: 'SSH OK', last_check: null }],
    ...overrides,
  }
}

beforeEach(() => {
  api.apiGet.mockReset().mockResolvedValue(detail())
  permissions.granted = new Set(['system.hosts', 'system.network_health'])
})

describe('StatusDetailDrawer Ports section', () => {
  it('shows the Ports section for a discovered device the user may view', async () => {
    render(<StatusDetailDrawer hostname="web-01" onClose={() => {}} />)

    expect(await screen.findByText('Ports section for device 4 (web-01)')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Services' })).toBeInTheDocument()       // existing sections are unchanged
    expect(screen.getByRole('heading', { name: 'Timestamps' })).toBeInTheDocument()
  })

  it('is shown after the services list', async () => {
    render(<StatusDetailDrawer hostname="web-01" onClose={() => {}} />)

    const ports = await screen.findByText(/Ports section/)
    const services = screen.getByRole('heading', { name: 'Services' })
    expect(services.compareDocumentPosition(ports) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it.each([[null], [undefined]])('is not shown when the host has no device record (%s)', async (deviceId) => {
    api.apiGet.mockResolvedValue(detail({ device_id: deviceId }))
    render(<StatusDetailDrawer hostname="localhost" onClose={() => {}} />)

    await screen.findByRole('heading', { name: 'Timestamps' })
    expect(screen.queryByText(/Ports section/)).not.toBeInTheDocument()
  })

  it('is not shown without system.hosts', async () => {
    permissions.granted = new Set(['system.network_health'])
    render(<StatusDetailDrawer hostname="web-01" onClose={() => {}} />)

    await screen.findByRole('heading', { name: 'Timestamps' })
    expect(screen.queryByText(/Ports section/)).not.toBeInTheDocument()
  })

  it('is not shown inside a service\'s own view', async () => {
    render(<StatusDetailDrawer hostname="web-01" onClose={() => {}} />)
    await screen.findByText(/Ports section/)
    api.apiGet.mockResolvedValue(detail({ service: 'ssh-22-tcp', services: undefined }))

    fireEvent.click(screen.getByRole('button', { name: /ssh-22-tcp/ }))

    await screen.findByText('web-01 / ssh-22-tcp')
    expect(screen.queryByText(/Ports section/)).not.toBeInTheDocument()
  })

  it('asks for the host detail by host name as before', async () => {
    render(<StatusDetailDrawer hostname="web-01" onClose={() => {}} />)
    await screen.findByText(/Ports section/)
    expect(api.apiGet).toHaveBeenCalledWith('/api/system/network-health/hosts/web-01/detail')
  })
})
