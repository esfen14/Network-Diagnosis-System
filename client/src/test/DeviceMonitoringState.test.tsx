import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DeviceMonitoringSection } from '../components/device-inventory/DeviceMonitoringSection'
import { HostTable } from '../components/device-inventory/HostTable'
import { fromHostRecord, type MonitoringState } from '../types/host'

const api = vi.hoisted(() => ({ pauseDevice: vi.fn(), resumeDevice: vi.fn() }))
vi.mock('../lib/deviceMonitoringApi', () => ({
  pauseDevice: (id: number) => api.pauseDevice(id),
  resumeDevice: (id: number) => api.resumeDevice(id),
}))

const permissions = vi.hoisted(() => ({ granted: new Set<string>() }))
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({ user: null, isLoading: false, hasPermission: (name: string) => permissions.granted.has(name) }),
}))

const OK = { config_applied: true, config_ok: true, config_message: 'applied', device: { id: 4, monitoring_state: 'paused', monitored: false } }

beforeEach(() => {
  api.pauseDevice.mockReset().mockResolvedValue(OK)
  api.resumeDevice.mockReset().mockResolvedValue({ ...OK, device: { id: 4, monitoring_state: 'monitored', monitored: true } })
  permissions.granted = new Set(['system.hosts', 'system.hosts.edit'])
})

function section(state: MonitoringState, onChanged = vi.fn()) {
  render(<DeviceMonitoringSection deviceId={4} hostname="web-01" state={state} onChanged={onChanged} />)
  return onChanged
}

describe('DeviceMonitoringSection', () => {
  it.each([
    ['monitored', 'Monitored', /Nagios is checking this device/],
    ['missing', 'Missing', /still being checked/],
    ['address_unknown', 'Address unknown', /belongs to another device/],
    ['paused', 'Paused', /administrator paused/],
    ['retired', 'Retired', /last one Nagios reported/],
    ['merged', 'Merged', /last one Nagios reported/],
  ] as const)('shows the label and reason for %s', (state, label, reason) => {
    section(state)

    expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.getByText(reason)).toBeInTheDocument()
  })

  it('pauses after a confirmation and tells the drawer to reload', async () => {
    const onChanged = section('monitored')

    await userEvent.click(screen.getByRole('button', { name: 'Pause monitoring' }))
    expect(api.pauseDevice).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog', { name: 'Confirm Pause monitoring' })).toHaveTextContent('Pause monitoring of web-01?')
    await userEvent.click(screen.getAllByRole('button', { name: 'Pause monitoring' })[1])

    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(api.pauseDevice).toHaveBeenCalledWith(4)
  })

  it('resumes a paused device', async () => {
    const onChanged = section('paused')

    await userEvent.click(screen.getByRole('button', { name: 'Resume monitoring' }))
    await userEvent.click(screen.getAllByRole('button', { name: 'Resume monitoring' })[1])

    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(api.resumeDevice).toHaveBeenCalledWith(4)
    expect(api.pauseDevice).not.toHaveBeenCalled()
  })

  it('does nothing when the confirmation is cancelled', async () => {
    section('monitored')

    await userEvent.click(screen.getByRole('button', { name: 'Pause monitoring' }))
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(api.pauseDevice).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it.each(['retired', 'merged'] as const)('offers no action for a %s device', (state) => {
    section(state)

    expect(screen.queryByRole('button', { name: /monitoring/ })).not.toBeInTheDocument()
  })

  it('offers no action without system.hosts.edit', () => {
    permissions.granted = new Set(['system.hosts'])
    section('monitored')

    expect(screen.getByText('Monitored')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pause monitoring' })).not.toBeInTheDocument()
  })

  it('warns when the change was saved but Nagios was not updated', async () => {
    api.pauseDevice.mockResolvedValue({ ...OK, config_ok: false, config_message: 'bad directive' })
    section('monitored')

    await userEvent.click(screen.getByRole('button', { name: 'Pause monitoring' }))
    await userEvent.click(screen.getAllByRole('button', { name: 'Pause monitoring' })[1])

    expect(await screen.findByText(/saved but Nagios was not updated: bad directive/)).toBeInTheDocument()
  })

  it('shows the server error and keeps the label when the change fails', async () => {
    api.pauseDevice.mockRejectedValue(new Error('Device is already paused.'))
    const onChanged = section('monitored')

    await userEvent.click(screen.getByRole('button', { name: 'Pause monitoring' }))
    await userEvent.click(screen.getAllByRole('button', { name: 'Pause monitoring' })[1])

    expect(await screen.findByText('Device is already paused.')).toBeInTheDocument()
    expect(onChanged).not.toHaveBeenCalled()
  })
})

function record(hostname: string, monitoring_state?: MonitoringState | null) {
  return fromHostRecord({
    hostname,
    monitoring_state,
    state: 'Up',
    state_type: 'HARD',
    last_check: null,
    check_latency: 0.01,
    plugin_output: 'OK',
    is_flapping: false,
    in_downtime: false,
    nagios_ack: 'none',
    ack: null,
  })
}

function table(onMonitoringFilterChange = vi.fn(), monitoringFilter: 'all' | MonitoringState = 'all') {
  render(
    <MemoryRouter>
      <HostTable
        hosts={[record('web-01', 'paused'), record('old-01', 'retired'), record('localhost', null), record('db-01', 'monitored')]}
        title="All Hosts"
        isLoading={false}
        query=""
        onQueryChange={() => {}}
        stateFilter="All"
        onStateFilterChange={() => {}}
        monitoringFilter={monitoringFilter}
        onMonitoringFilterChange={onMonitoringFilterChange}
        showFilter
        onToggleFilter={() => {}}
        sortAsc
        onToggleSort={() => {}}
        page={1}
        pageCount={1}
        total={4}
        hasNext={false}
        hasPrev={false}
        onPageChange={() => {}}
        onAcknowledge={() => {}}
        onUnacknowledge={() => {}}
      />
    </MemoryRouter>
  )
  return onMonitoringFilterChange
}

describe('HostTable monitoring column and filter', () => {
  it('maps the server field and defaults to null', () => {
    expect(record('a', 'paused').monitoringState).toBe('paused')
    expect(record('a').monitoringState).toBeNull()
  })

  it('shows a chip per host, a dash for a host with no device, and marks a stale snapshot', () => {
    table()

    const row = (name: string) => screen.getByText(name).closest('tr') as HTMLElement
    expect(row('web-01')).toHaveTextContent('Paused')
    expect(row('db-01')).toHaveTextContent('Monitored')
    expect(row('old-01')).toHaveTextContent('Retired')
    expect(row('old-01')).toHaveTextContent('last known status')
    expect(row('web-01')).toHaveTextContent('last known status')
    expect(row('db-01')).not.toHaveTextContent('last known status')
    expect(row('localhost')).not.toHaveTextContent(/Monitored|Paused|Retired/)
  })

  it('offers the monitoring filters and reports the choice', async () => {
    const onChange = table()

    for (const label of ['Not monitored', 'Address unknown', 'Merged']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
    await userEvent.click(screen.getByRole('button', { name: 'Not monitored' }))

    expect(onChange).toHaveBeenCalledWith('not_monitored')
  })
})
