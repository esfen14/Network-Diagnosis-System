import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { PluginServicesSection } from '../components/plugin-manager/PluginServicesSection'
import type { PluginServiceItem, PluginServicesResponse, ServiceStatusKind } from '../types/plugin'

const api = vi.hoisted(() => ({
  getPluginServices: vi.fn(),
  stopServiceMonitoring: vi.fn(),
  resumeServiceMonitoring: vi.fn(),
}))
vi.mock('../lib/pluginApi', () => api)

const permissions = vi.hoisted(() => ({ granted: new Set<string>() }))
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({ user: null, isLoading: false, hasPermission: (name: string) => permissions.granted.has(name) }),
}))

function item(overrides: Partial<PluginServiceItem> = {}, kind: ServiceStatusKind = 'ok', output = 'SSH OK - 0.012s response'): PluginServiceItem {
  return {
    id: 8,
    service: 'ssh-22-tcp',
    device: { id: 4, hostname: 'web-01', ip_address: '192.168.130.20' },
    port: 22,
    protocol: 'tcp',
    metric: null,
    monitored: true,
    running_since: '2026-10-05T09:30:00+00:00',
    status: { kind, state: kind === 'ok' ? 'OK' : null, output, last_check: '2026-10-05T09:35:00+00:00' },
    ...overrides,
  }
}

function response(items: PluginServiceItem[], overrides: Partial<PluginServicesResponse> = {}): PluginServicesResponse {
  return { items, page: 1, per_page: 5, pages: 1, total: items.length, has_next: false, has_prev: false, ...overrides }
}

function renderSection(onChanged = vi.fn(), refreshKey = 0) {
  return render(<PluginServicesSection pluginId={3} refreshKey={refreshKey} onChanged={onChanged} />)
}

describe('PluginServicesSection', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    permissions.granted = new Set(['plugin.enable', 'plugin.disable'])
    api.getPluginServices.mockResolvedValue(response([item()]))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('lists the service, device, IP, status, output and running since', async () => {
    renderSection()

    expect(await screen.findByText('ssh-22-tcp')).toBeInTheDocument()
    expect(screen.getByText(/web-01 · 192\.168\.130\.20/)).toBeInTheDocument()
    expect(screen.getByText('OK')).toBeInTheDocument()
    expect(screen.getByText('SSH OK - 0.012s response')).toBeInTheDocument()
    expect(screen.getByText(/Running since/)).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 1 · 1 service')).toBeInTheDocument()
    expect(api.getPluginServices).toHaveBeenCalledWith(3, { page: 1, per_page: 5, search: '' })
  })

  it.each([
    ['ok', 'OK'], ['warning', 'Warning'], ['critical', 'Critical'], ['unknown', 'Unknown'],
    ['waiting', 'Waiting'], ['stale', 'No recent data'], ['stopped', 'Stopped'],
  ] as [ServiceStatusKind, string][])('labels a %s service', async (kind, label) => {
    api.getPluginServices.mockResolvedValue(response([item({}, kind, `output for ${kind}`)]))
    renderSection()

    expect(await screen.findByText(label)).toBeInTheDocument()
    expect(screen.getByText(`output for ${kind}`)).toBeInTheDocument()
  })

  it('says how to get services when there are none', async () => {
    api.getPluginServices.mockResolvedValue(response([]))
    renderSection()

    expect(await screen.findByText(/No services yet/)).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 1 · 0 services')).toBeInTheDocument()
  })

  it('shows the server message when the list cannot be loaded', async () => {
    api.getPluginServices.mockRejectedValue(new ApiError('Plugin not found.', 404))
    renderSection()

    expect(await screen.findByText('Plugin not found.')).toBeInTheDocument()
  })

  it('searches after a pause and returns to the first page', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderSection()
    await screen.findByText('ssh-22-tcp')

    fireEvent.change(screen.getByLabelText('Search monitored services'), { target: { value: 'db-' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(400) })

    await waitFor(() => expect(api.getPluginServices).toHaveBeenLastCalledWith(3, { page: 1, per_page: 5, search: 'db-' }))
  })

  it('says nothing matched a search', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderSection()
    await screen.findByText('ssh-22-tcp')
    api.getPluginServices.mockResolvedValue(response([]))

    fireEvent.change(screen.getByLabelText('Search monitored services'), { target: { value: 'zzz' } })
    await act(async () => { await vi.advanceTimersByTimeAsync(400) })

    expect(await screen.findByText('No monitored services match your search.')).toBeInTheDocument()
  })

  it('pages through the list', async () => {
    api.getPluginServices.mockResolvedValue(response([item()], { pages: 3, total: 11, has_next: true }))
    renderSection()
    await screen.findByText('ssh-22-tcp')

    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => expect(api.getPluginServices).toHaveBeenLastCalledWith(3, { page: 2, per_page: 5, search: '' }))
  })

  it('reloads when the drawer bumps the refresh key', async () => {
    const { rerender } = renderSection(vi.fn(), 0)
    await screen.findByText('ssh-22-tcp')

    rerender(<PluginServicesSection pluginId={3} refreshKey={1} onChanged={vi.fn()} />)

    await waitFor(() => expect(api.getPluginServices).toHaveBeenCalledTimes(2))
  })

  describe('stopping and resuming one device', () => {
    it('stops monitoring the port, reloads the list and tells the page', async () => {
      api.stopServiceMonitoring.mockResolvedValue({ changed: true, monitored: false })
      const onChanged = vi.fn()
      renderSection(onChanged)

      fireEvent.click(await screen.findByRole('button', { name: 'Stop monitoring ssh-22-tcp on web-01' }))

      await waitFor(() => expect(onChanged).toHaveBeenCalled())
      expect(api.stopServiceMonitoring).toHaveBeenCalledWith(3, { device_id: 4, protocol: 'tcp', port: 22 })
      expect(api.getPluginServices).toHaveBeenCalledTimes(2)
    })

    it('resumes a stopped port', async () => {
      api.getPluginServices.mockResolvedValue(response([
        item({ id: null, monitored: false, running_since: null }, 'stopped', 'Monitoring stopped for this device.'),
      ]))
      api.resumeServiceMonitoring.mockResolvedValue({ changed: true, monitored: true })
      renderSection()

      expect(await screen.findByText('Not monitored')).toBeInTheDocument()
      fireEvent.click(screen.getByRole('button', { name: 'Resume monitoring ssh-22-tcp on web-01' }))

      await waitFor(() => expect(api.resumeServiceMonitoring).toHaveBeenCalledWith(3, { device_id: 4, protocol: 'tcp', port: 22 }))
      expect(api.stopServiceMonitoring).not.toHaveBeenCalled()
    })

    it('shows why a change was refused and keeps the list', async () => {
      api.stopServiceMonitoring.mockRejectedValue(new ApiError('Config failed to validate: bad directive', 409))
      const onChanged = vi.fn()
      renderSection(onChanged)

      fireEvent.click(await screen.findByRole('button', { name: /Stop monitoring/ }))

      expect(await screen.findByRole('alert')).toHaveTextContent('Config failed to validate: bad directive')
      expect(onChanged).not.toHaveBeenCalled()
      expect(screen.getByText('ssh-22-tcp')).toBeInTheDocument()
    })

    it('disables the button while the change is running', async () => {
      let finish: (value: unknown) => void = () => {}
      api.stopServiceMonitoring.mockReturnValue(new Promise((resolve) => { finish = resolve }))
      renderSection()

      const button = await screen.findByRole('button', { name: /Stop monitoring/ })
      fireEvent.click(button)

      await waitFor(() => expect(button).toBeDisabled())
      await act(async () => { finish({ changed: true, monitored: false }) })
      await waitFor(() => expect(screen.getByRole('button', { name: /Stop monitoring/ })).not.toBeDisabled())
    })

    it('hides Stop without plugin.disable and Resume without plugin.enable', async () => {
      permissions.granted = new Set(['plugin.enable'])
      api.getPluginServices.mockResolvedValue(response([
        item(),
        item({ id: null, service: 'http-80-tcp', port: 80, monitored: false }, 'stopped', 'Monitoring stopped for this device.'),
      ]))
      renderSection()

      await screen.findByText('http-80-tcp')
      expect(screen.queryByRole('button', { name: /Stop monitoring/ })).not.toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Resume monitoring/ })).toBeInTheDocument()
    })

    it('acts on the right row when two devices share a service name', async () => {
      api.getPluginServices.mockResolvedValue(response([
        item(),
        item({ id: 9, device: { id: 5, hostname: 'db-01', ip_address: '192.168.130.21' } }),
      ]))
      api.stopServiceMonitoring.mockResolvedValue({ changed: true, monitored: false })
      renderSection()

      const second = (await screen.findByText(/db-01/)).closest('div.rounded-xl') as HTMLElement
      fireEvent.click(within(second).getByRole('button', { name: /Stop monitoring/ }))

      await waitFor(() => expect(api.stopServiceMonitoring).toHaveBeenCalledWith(3, { device_id: 5, protocol: 'tcp', port: 22 }))
    })
  })
})
