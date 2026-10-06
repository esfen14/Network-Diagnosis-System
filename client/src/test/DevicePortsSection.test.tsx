import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { DevicePortsSection } from '../components/device-inventory/DevicePortsSection'
import type { DevicePort, PortReasonCode } from '../types/devicePorts'
import { port, ports } from './devicePortsFixtures'

const api = vi.hoisted(() => ({ getDevicePorts: vi.fn(), changePort: vi.fn() }))
vi.mock('../lib/devicePortsApi', () => api)

const permissions = vi.hoisted(() => ({ granted: new Set<string>() }))
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({ user: null, isLoading: false, hasPermission: (name: string) => permissions.granted.has(name) }),
}))

const ok = { config_applied: true, config_ok: true, config_message: 'applied', port: {} }

const suggested = (code: PortReasonCode, overrides: Partial<DevicePort> = {}) =>
  port({ state: 'SUGGESTED', reason: { code, text: `reason text for ${code}` }, ...overrides })

function renderSection() {
  return render(
    <MemoryRouter>
      <DevicePortsSection deviceId={4} hostname="web-01" />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.getDevicePorts.mockReset().mockResolvedValue(ports([port()]))
  api.changePort.mockReset().mockResolvedValue(ok)
  permissions.granted = new Set(['system.hosts', 'system.hosts.edit', 'plugin.view'])
})

describe('states of the section', () => {
  it('shows a loading indicator first', async () => {
    api.getDevicePorts.mockReturnValue(new Promise(() => {}))
    renderSection()
    expect(screen.getByText('Loading ports…')).toBeInTheDocument()
  })

  it('shows the error with Retry, and Retry loads again', async () => {
    api.getDevicePorts.mockRejectedValueOnce(new ApiError('Device not found.', 404))
    renderSection()

    expect(await screen.findByText('Device not found.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('tcp/22')).toBeInTheDocument()
    expect(api.getDevicePorts).toHaveBeenCalledTimes(2)
  })

  it('says when no ports were discovered', async () => {
    api.getDevicePorts.mockResolvedValue(ports([]))
    renderSection()

    expect(await screen.findByText('No ports discovered yet. Run a scan from Network Discovery.')).toBeInTheDocument()
  })

  it('loads the ports of the device it is given', async () => {
    renderSection()
    await screen.findByText('tcp/22')
    expect(api.getDevicePorts).toHaveBeenCalledWith(4)
  })

  it('says the user can only view when they lack system.hosts.edit', async () => {
    permissions.granted = new Set(['system.hosts'])
    renderSection()

    expect(await screen.findByText('You can view ports but not change them.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Stop monitoring/ })).not.toBeInTheDocument()
  })

  it.each([['RETIRED', 'retired'], ['MERGED', 'merged']] as const)('is read-only for a %s device', async (state, word) => {
    api.getDevicePorts.mockResolvedValue(ports([port()], { state }))
    renderSection()

    expect(await screen.findByText(`This device is ${word}.`)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Stop monitoring/ })).not.toBeInTheDocument()
  })
})

describe('groups and rows', () => {
  it('shows the groups in order with counts and leaves empty ones out', async () => {
    api.getDevicePorts.mockResolvedValue(ports([
      port({ number: 22 }),
      port({ number: 8080, state: 'IGNORED', reason: { code: 'stopped', text: 'Monitoring stopped by an administrator.' } }),
      suggested('held', { number: 9100 }),
      suggested('plugin_not_enabled', { number: 3306 }),
      port({ number: 443, state: 'ARCHIVED' }),
    ]))
    renderSection()

    await screen.findByText('tcp/22')
    const headings = screen.getAllByRole('heading', { level: 4 }).map((h) => h.textContent)
    expect(headings).toEqual(['Needs attention (1)', 'Monitored (1)', 'Suggested (1)', 'Stopped (1)'])
    expect(screen.getByRole('button', { name: /Archived \(1\)/ })).toBeInTheDocument()
    expect(screen.queryByText('Stopped (0)')).not.toBeInTheDocument()
  })

  it('summarises the counts per state', async () => {
    api.getDevicePorts.mockResolvedValue(ports([port(), port({ number: 80 }), suggested('guessed', { number: 5 })]))
    renderSection()

    expect(await screen.findByText('2 monitored · 1 suggested')).toBeInTheDocument()
  })

  it('shows a row with its port, service, state, identification, check plugin and last seen', async () => {
    renderSection()

    const row = (await screen.findByText('tcp/22')).closest('li')!
    expect(within(row).getByText('ssh')).toBeInTheDocument()
    expect(within(row).getByText('Monitored')).toBeInTheDocument()
    expect(within(row).getByText(/Fingerprint · Check: check_ssh/)).toBeInTheDocument()
    expect(within(row).getByText(/Last seen/)).toBeInTheDocument()
    expect(within(row).getByText(/Last seen/).getAttribute('title')).toBeTruthy()
  })

  it('says "none" when no plugin can check the service', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('no_udp_plugin', { protocol: 'udp', number: 9999, check_plugin: null })]))
    renderSection()

    expect(await screen.findByText(/Check: none/)).toBeInTheDocument()
  })

  it('marks a missing port as not seen lately', async () => {
    api.getDevicePorts.mockResolvedValue(ports([port({ state: 'MISSING' })]))
    renderSection()

    expect(await screen.findByText('Missing')).toBeInTheDocument()
    expect(screen.getByText('not seen lately')).toBeInTheDocument()
  })

  it('shows a flagged port as not used as intended, with what was found and expected', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('not_used_as_intended', {
      number: 22, service_name: 'http', expected_service_name: 'ssh',
    })]))
    renderSection()

    const row = (await screen.findByText('tcp/22')).closest('li')!
    expect(within(row).getByText('Not used as intended')).toBeInTheDocument()
    expect(within(row).getByText('found http, expected ssh')).toBeInTheDocument()
  })

  it('does not call an acknowledged port not used as intended', async () => {
    api.getDevicePorts.mockResolvedValue(ports([port({ expected_service_name: 'ssh', mismatch_acknowledged: true, service_name: 'http' })]))
    renderSection()

    await screen.findByText('tcp/22')
    expect(screen.queryByText('Not used as intended')).not.toBeInTheDocument()
  })

  it('shows a held port as held', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('held', { promotion_held: true })]))
    renderSection()

    expect(await screen.findByText('Held')).toBeInTheDocument()
  })

  it.each([
    ['PORT_RULE', 'Port rule'], ['USER', 'Pinned'], ['PORT_HINT', 'Guess'],
  ] as const)('labels how a %s port was identified', async (identified_by, label) => {
    api.getDevicePorts.mockResolvedValue(ports([port({ identified_by })]))
    renderSection()

    expect(await screen.findByText(new RegExp(`${label} · Check`))).toBeInTheDocument()
  })

  it.each([
    'not_used_as_intended', 'held', 'guessed', 'no_udp_plugin', 'plugin_not_enabled', 'device_excluded', 'pending', 'missing', 'monitoring_inactive',
  ] as PortReasonCode[])('shows the server\'s reason text for %s', async (code) => {
    api.getDevicePorts.mockResolvedValue(ports([suggested(code)]))
    renderSection()

    expect(await screen.findByText(new RegExp(`reason text for ${code}`))).toBeInTheDocument()
  })

  it('shows no reason for a monitored port', async () => {
    renderSection()
    await screen.findByText('tcp/22')
    expect(screen.queryByText(/reason text/)).not.toBeInTheDocument()
  })

  it('keeps Archived collapsed with no actions until opened', async () => {
    api.getDevicePorts.mockResolvedValue(ports([port({ number: 443, state: 'ARCHIVED' })]))
    renderSection()

    const toggle = await screen.findByRole('button', { name: /Archived \(1\)/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('tcp/443')).not.toBeInTheDocument()

    fireEvent.click(toggle)

    expect(screen.getByText('tcp/443')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /on web-01/ })).not.toBeInTheDocument()
  })

  it('says a deployed NCPA port is managed by NCPA deployment and offers nothing on it', async () => {
    api.getDevicePorts.mockResolvedValue(ports([port({ number: 5693, service_name: 'ncpa', managed_by_ncpa: true, pinned: true })]))
    renderSection()

    expect(await screen.findByText('Managed by NCPA deployment')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /on web-01/ })).not.toBeInTheDocument()
  })
})

describe('Plugin Manager link', () => {
  const notEnabled = () => ports([suggested('plugin_not_enabled', { number: 3306, service_name: 'mysql', check_plugin: 'check_mysql' })])

  it('links to Plugin Manager for users who can view it', async () => {
    api.getDevicePorts.mockResolvedValue(notEnabled())
    renderSection()

    const link = await screen.findByRole('link', { name: 'Enable check_mysql' })
    expect(link).toHaveAttribute('href', '/plugins')
  })

  it('does not link for a user without plugin.view', async () => {
    permissions.granted = new Set(['system.hosts', 'system.hosts.edit'])
    api.getDevicePorts.mockResolvedValue(notEnabled())
    renderSection()

    await screen.findByText(/reason text for plugin_not_enabled/)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })

  it('links only for the plugin-not-enabled reason', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('held')]))
    renderSection()

    await screen.findByText(/reason text for held/)
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})

describe('actions that do not ask first', () => {
  const click = async (name: RegExp | string) => fireEvent.click(await screen.findByRole('button', { name }))

  it('Monitor sends state MONITORED and reloads', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('plugin_not_enabled', { number: 3306 })]))
    renderSection()

    await click('Monitor tcp/3306 on web-01')

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'tcp', 3306, { state: 'MONITORED' }))
    await waitFor(() => expect(api.getDevicePorts).toHaveBeenCalledTimes(2))
  })

  it('Acknowledge and monitor sends acknowledge_mismatch, and Monitor is not offered beside it', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('not_used_as_intended', { service_name: 'http', expected_service_name: 'ssh' })]))
    renderSection()

    await screen.findByText('tcp/22')
    expect(screen.queryByRole('button', { name: /^Monitor tcp/ })).not.toBeInTheDocument()
    await click('Acknowledge and monitor tcp/22 on web-01')

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'tcp', 22, { acknowledge_mismatch: true }))
  })

  it('Monitor on a held port releases it with state MONITORED', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('held', { promotion_held: true })]))
    renderSection()

    await click('Monitor tcp/22 on web-01')

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'tcp', 22, { state: 'MONITORED' }))
  })

  it('Resume sends state MONITORED for a stopped port', async () => {
    api.getDevicePorts.mockResolvedValue(ports([port({ state: 'IGNORED', reason: { code: 'stopped', text: 'Monitoring stopped by an administrator.' } })]))
    renderSection()

    await click('Resume tcp/22 on web-01')

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'tcp', 22, { state: 'MONITORED' }))
  })

  it('UDP ports use the udp protocol in the request', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('pending', { protocol: 'udp', number: 161, service_name: 'snmp' })]))
    renderSection()

    await click('Monitor udp/161 on web-01')

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'udp', 161, { state: 'MONITORED' }))
  })
})

describe('actions that ask first', () => {
  const open = async (button: string) => fireEvent.click(await screen.findByRole('button', { name: button }))

  it('Stop monitoring shows the wording, sends nothing until confirmed, then sends IGNORED', async () => {
    renderSection()

    await open('Stop monitoring tcp/22 on web-01')

    const dialog = screen.getByRole('dialog', { name: 'Confirm Stop monitoring' })
    expect(within(dialog).getByText('Stop monitoring ssh on web-01? Its Nagios service is removed; history is kept.')).toBeInTheDocument()
    expect(api.changePort).not.toHaveBeenCalled()

    fireEvent.click(within(dialog).getByRole('button', { name: 'Stop monitoring' }))

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'tcp', 22, { state: 'IGNORED' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('Ignore on a Suggested port asks and then sends IGNORED', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('guessed', { number: 8080 })]))
    renderSection()

    await open('Ignore tcp/8080 on web-01')
    expect(screen.getByText('Ignore tcp/8080 on web-01? It will not be monitored.')).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Ignore' }))

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'tcp', 8080, { state: 'IGNORED' }))
  })

  it('Leave suggested asks and then sends SUGGESTED', async () => {
    renderSection()

    await open('Leave suggested tcp/22 on web-01')
    expect(screen.getByText(
      'Leave tcp/22 suggested? Its Nagios service is removed and no plugin will monitor it again until you do.')).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Leave suggested' }))

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'tcp', 22, { state: 'SUGGESTED' }))
  })

  it('Cancel changes nothing', async () => {
    renderSection()

    await open('Stop monitoring tcp/22 on web-01')
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.changePort).not.toHaveBeenCalled()
    expect(api.getDevicePorts).toHaveBeenCalledTimes(1)
  })

  it('Remove pin on a monitored port says its Nagios service is not changed', async () => {
    api.getDevicePorts.mockResolvedValue(ports([port({ pinned: true, identified_by: 'USER' })]))
    renderSection()

    await open('Remove pin tcp/22 on web-01')

    const dialog = screen.getByRole('dialog', { name: 'Confirm Remove pin' })
    expect(within(dialog).getByText(/Let scans decide the service for tcp\/22 on web-01 again\?/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Its Nagios service is not changed/)).toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Remove pin' }))

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'tcp', 22, { unpin: true }))
  })

  it('Remove pin on a suggested port says it goes back to the last scan', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('held', { pinned: true, identified_by: 'USER' })]))
    renderSection()

    await open('Remove pin tcp/22 on web-01')

    expect(screen.getByText(/The service goes back to what the last scan saw\./)).toBeInTheDocument()
  })

  it('offers Remove pin only on a pinned port', async () => {
    renderSection()
    await screen.findByText('tcp/22')
    expect(screen.queryByRole('button', { name: /Remove pin/ })).not.toBeInTheDocument()
  })
})

describe('results of an action', () => {
  const stop = async () => {
    fireEvent.click(await screen.findByRole('button', { name: 'Stop monitoring tcp/22 on web-01' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Stop monitoring' }))
  }

  it('shows a change that was saved but is not in Nagios yet', async () => {
    api.changePort.mockResolvedValue({ ...ok, config_applied: false, config_ok: false, config_message: 'Config failed to validate: bad directive' })
    renderSection()

    await stop()

    expect(await screen.findByRole('status')).toHaveTextContent(
      'The change was saved but Nagios was not updated: Config failed to validate: bad directive')
  })

  it('says nothing when there was nothing to reload', async () => {
    api.changePort.mockResolvedValue({ ...ok, config_applied: false, config_ok: true, config_message: 'Host configuration unchanged; Nagios was not reloaded.' })
    renderSection()

    await stop()

    await waitFor(() => expect(api.getDevicePorts).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('shows the server\'s message when a change is refused and changes nothing', async () => {
    api.changePort.mockRejectedValue(new ApiError('The NCPA port cannot be removed while an NCPA token is deployed.', 400))
    renderSection()

    await stop()

    expect(await screen.findByRole('alert')).toHaveTextContent('The NCPA port cannot be removed while an NCPA token is deployed.')
    expect(api.getDevicePorts).toHaveBeenCalledTimes(1)
    expect(screen.getByText('tcp/22')).toBeInTheDocument()
  })

  it('clears an earlier message when the next action starts', async () => {
    api.changePort.mockRejectedValueOnce(new ApiError('first failure', 409))
    renderSection()
    await stop()
    expect(await screen.findByRole('alert')).toHaveTextContent('first failure')

    await stop()

    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })

  it('disables the row\'s buttons while a change is running and enables them after', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('pending')]))
    let finish: (value: unknown) => void = () => {}
    api.changePort.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    renderSection()

    const button = await screen.findByRole('button', { name: 'Monitor tcp/22 on web-01' })
    fireEvent.click(button)

    await waitFor(() => expect(button).toBeDisabled())
    expect(screen.getByRole('button', { name: 'Ignore tcp/22 on web-01' })).toBeDisabled()
    await act(async () => { finish(ok) })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Monitor tcp/22 on web-01' })).not.toBeDisabled())
  })

  it('only the row being changed is disabled', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('pending', { number: 22 }), suggested('pending', { number: 80 })]))
    api.changePort.mockReturnValue(new Promise(() => {}))
    renderSection()

    fireEvent.click(await screen.findByRole('button', { name: 'Monitor tcp/22 on web-01' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Monitor tcp/22 on web-01' })).toBeDisabled())
    expect(screen.getByRole('button', { name: 'Monitor tcp/80 on web-01' })).not.toBeDisabled()
  })
})

describe('Set service', () => {
  const openDialog = async (overrides: Partial<DevicePort> = {}) => {
    api.getDevicePorts.mockResolvedValue(ports([port({ number: 8080, service_name: 'http-proxy', ...overrides })]))
    renderSection()
    fireEvent.click(await screen.findByRole('button', { name: 'Set service… tcp/8080 on web-01' }))
    return screen.getByRole('dialog', { name: 'Set service for tcp/8080 on web-01' })
  }
  const type = (dialog: HTMLElement, value: string) =>
    fireEvent.change(within(dialog).getByLabelText('Service name'), { target: { value } })

  it('opens with the current service and always says what a pin means', async () => {
    const dialog = await openDialog()

    expect(within(dialog).getByLabelText('Service name')).toHaveValue('http-proxy')
    expect(within(dialog).getByText(/Scans will no longer change this port's service on this device\. You can change it again or use Remove pin\./)).toBeInTheDocument()
  })

  it('suggests the services Pinpoint knows for the port\'s protocol', async () => {
    const dialog = await openDialog()
    const values = Array.from(dialog.querySelectorAll('datalist option')).map((o) => o.getAttribute('value'))

    expect(values).toEqual(['http', 'ssh'])          // the udp-only snmp is not offered for a TCP port
  })

  it('warns that a monitored port\'s Nagios service will be renamed', async () => {
    const dialog = await openDialog()
    expect(within(dialog).getByText(/Its Nagios service will be renamed/)).toBeInTheDocument()
    expect(within(dialog).getByText(/History stays under the old name/)).toBeInTheDocument()
  })

  it('does not warn about renaming for a port that is not monitored', async () => {
    const dialog = await openDialog({ state: 'SUGGESTED', reason: { code: 'guessed', text: 'g' } })
    expect(within(dialog).queryByText(/Its Nagios service will be renamed/)).not.toBeInTheDocument()
  })

  it('shows which check a known service leads to', async () => {
    const dialog = await openDialog()
    type(dialog, 'ssh')
    expect(within(dialog).getByText(/Checked by:/)).toHaveTextContent('Checked by: check_ssh')
  })

  it('shows the generic TCP check for an unknown TCP name', async () => {
    const dialog = await openDialog()
    type(dialog, 'printer')
    expect(within(dialog).getByText('check_tcp (generic TCP check)')).toBeInTheDocument()
  })

  it('says an unknown UDP name is skipped', async () => {
    api.getDevicePorts.mockResolvedValue(ports([port({ protocol: 'udp', number: 9999, service_name: 'mystery' })]))
    renderSection()
    fireEvent.click(await screen.findByRole('button', { name: 'Set service… udp/9999 on web-01' }))
    const dialog = screen.getByRole('dialog')

    type(dialog, 'printer')

    expect(within(dialog).getByText('Skipped: no check exists for this UDP service')).toBeInTheDocument()
  })

  it.each(['SSH', '-ssh', 'has space', 'ssh;rm', 'a'.repeat(33)])('rejects %j and disables Save', async (name) => {
    const dialog = await openDialog()

    type(dialog, name)

    expect(within(dialog).getByText(/Use lowercase letters, digits/)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(within(dialog).queryByText('check_tcp (generic TCP check)')).not.toBeInTheDocument()
  })

  it('disables Save for an empty name without scolding', async () => {
    const dialog = await openDialog()
    type(dialog, '')
    expect(within(dialog).getByRole('button', { name: 'Save' })).toBeDisabled()
    expect(within(dialog).queryByText(/Use lowercase letters/)).not.toBeInTheDocument()
  })

  it('disables Save while the name is unchanged', async () => {
    const dialog = await openDialog()
    expect(within(dialog).getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('saves the new name, closes and reloads', async () => {
    const dialog = await openDialog()
    type(dialog, '  ssh ')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(api.changePort).toHaveBeenCalledWith(4, 'tcp', 8080, { service_name: 'ssh' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(api.getDevicePorts).toHaveBeenCalledTimes(2))
  })

  it('keeps the dialog open and shows the server\'s message when the save is refused', async () => {
    api.changePort.mockRejectedValue(new ApiError('service_name must be lowercase letters, digits, \'-\' or \'_\'.', 400))
    const dialog = await openDialog()
    type(dialog, 'ssh')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Save' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('service_name must be lowercase')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(api.getDevicePorts).toHaveBeenCalledTimes(1)
  })

  it('Cancel closes without saving', async () => {
    const dialog = await openDialog()
    type(dialog, 'ssh')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.changePort).not.toHaveBeenCalled()
  })

  it('is offered on a Suggested port too, and not on an Archived one', async () => {
    api.getDevicePorts.mockResolvedValue(ports([suggested('held', { number: 9100 }), port({ number: 443, state: 'ARCHIVED' })]))
    renderSection()

    expect(await screen.findByRole('button', { name: 'Set service… tcp/9100 on web-01' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Archived/ }))
    expect(screen.queryByRole('button', { name: /Set service… tcp\/443/ })).not.toBeInTheDocument()
  })
})
