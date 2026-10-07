import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PluginSettings } from '../components/settings/PluginSettings'
import { ApiError } from '../lib/api'

const getPluginSettings = vi.fn()
const savePluginSettings = vi.fn()

vi.mock('../lib/pluginSettingsApi', () => ({
  getPluginSettings: () => getPluginSettings(),
  savePluginSettings: (...args: unknown[]) => savePluginSettings(...args),
}))

const OIDS = [
  { metric: 'uptime', oid: '1.3.6.1.2.1.1.3.0' },
  { metric: 'system_description', oid: '1.3.6.1.2.1.1.1.0' },
]

const METRICS = [
  { metric: 'cpu', path: 'cpu/percent', warning: '50', critical: '80', queryargs: 'aggregate=avg' },
  { metric: 'disk', path: 'disk/logical/{partition}/used_percent', warning: '70', critical: '95' },
]

function snmp(overrides: Record<string, unknown> = {}) {
  return {
    plugin: 'check_snmp',
    installed: true,
    status: 'Active',
    settings: { oids: OIDS },
    defaults: { oids: OIDS },
    version: 0,
    ...overrides,
  }
}

function ncpa(overrides: Record<string, unknown> = {}) {
  return {
    plugin: 'check_ncpa',
    installed: true,
    status: 'Enabled',
    settings: { metrics: METRICS },
    defaults: { metrics: METRICS },
    version: 0,
    ...overrides,
  }
}

async function renderLoaded(snmpOverrides: Record<string, unknown> = {}, ncpaOverrides: Record<string, unknown> = {}) {
  getPluginSettings.mockResolvedValue({ snmp: snmp(snmpOverrides), ncpa: ncpa(ncpaOverrides) })
  render(<PluginSettings />)
  await waitFor(() => expect(screen.queryByText(/Loading plugin settings/)).not.toBeInTheDocument())
}

function card(title: string) {
  return screen.getByText(title).closest('section') as HTMLElement
}

function save(title: string) {
  fireEvent.click(within(card(title)).getByRole('button', { name: /save changes/i }))
}

describe('PluginSettings: SNMP', () => {
  beforeEach(() => {
    getPluginSettings.mockReset()
    savePluginSettings.mockReset()
  })

  it('shows the OID table with each description and OID', async () => {
    await renderLoaded()

    const snmpCard = within(card('SNMP OIDs'))
    expect(snmpCard.getByLabelText('Description 1')).toHaveValue('uptime')
    expect(snmpCard.getByLabelText('OID 1')).toHaveValue('1.3.6.1.2.1.1.3.0')
    expect(snmpCard.getByLabelText('Description 2')).toHaveValue('system_description')
  })

  it('hides the table until check_snmp is installed', async () => {
    await renderLoaded({ installed: false, status: null })

    expect(screen.queryByText('SNMP OIDs')).not.toBeInTheDocument()
    expect(screen.getByText(/SNMP OIDs table appears here once check_snmp is installed/)).toBeInTheDocument()
  })

  it('warns when check_snmp is installed but not enabled', async () => {
    await renderLoaded({ status: 'Ready' })

    expect(within(card('SNMP OIDs')).getByText(/check_snmp is Ready/)).toBeInTheDocument()
  })

  it('changes an OID in place and saves the table with its version', async () => {
    await renderLoaded({ version: 3 })
    const changed = [{ metric: 'uptime', oid: '1.3.6.1.2.1.25.1.1.0' }, OIDS[1]]
    savePluginSettings.mockResolvedValue({ ...snmp({ settings: { oids: changed }, version: 4 }), config_ok: true, config_applied: true, config_message: 'ok' })

    fireEvent.change(within(card('SNMP OIDs')).getByLabelText('OID 1'), { target: { value: '1.3.6.1.2.1.25.1.1.0' } })
    save('SNMP OIDs')

    await waitFor(() => expect(savePluginSettings).toHaveBeenCalledWith('snmp', 'oids', changed, 3))
  })

  it('adds and removes rows, and warns that a new description makes a new service', async () => {
    await renderLoaded()
    const snmpCard = within(card('SNMP OIDs'))

    fireEvent.click(snmpCard.getByRole('button', { name: 'Add OID' }))
    fireEvent.change(snmpCard.getByLabelText('Description 3'), { target: { value: 'CPU_Load' } })
    fireEvent.change(snmpCard.getByLabelText('OID 3'), { target: { value: '1.3.6.1.4.1.2021.10.1.3.1' } })
    fireEvent.click(snmpCard.getByRole('button', { name: 'Remove system_description' }))

    expect(snmpCard.getByLabelText('Description 2')).toHaveValue('cpu_load')
    expect(snmpCard.queryByDisplayValue('system_description')).not.toBeInTheDocument()
    expect(snmpCard.getByText(/creates a new Nagios service on every SNMP device/)).toBeInTheDocument()
  })

  it('does not save a duplicate description or a bad OID', async () => {
    await renderLoaded()
    const snmpCard = within(card('SNMP OIDs'))

    fireEvent.change(snmpCard.getByLabelText('Description 2'), { target: { value: 'uptime' } })
    save('SNMP OIDs')
    expect(snmpCard.getByText('Description "uptime" is used more than once.')).toBeInTheDocument()

    fireEvent.change(snmpCard.getByLabelText('Description 2'), { target: { value: 'name' } })
    fireEvent.change(snmpCard.getByLabelText('OID 1'), { target: { value: '1.3.six' } })
    save('SNMP OIDs')
    expect(snmpCard.getByText(/OID for "uptime" must be numeric and dotted/)).toBeInTheDocument()
    expect(savePluginSettings).not.toHaveBeenCalled()
  })

  it('does not save an empty new row', async () => {
    await renderLoaded()

    fireEvent.click(within(card('SNMP OIDs')).getByRole('button', { name: 'Add OID' }))
    save('SNMP OIDs')

    expect(within(card('SNMP OIDs')).getByText('Row 3: Description is required.')).toBeInTheDocument()
    expect(savePluginSettings).not.toHaveBeenCalled()
  })

  it('resets to the config.py defaults', async () => {
    await renderLoaded({ settings: { oids: [{ metric: 'custom', oid: '1.3.6.1.1' }] } })
    const snmpCard = within(card('SNMP OIDs'))

    fireEvent.click(snmpCard.getByRole('button', { name: /reset to defaults/i }))

    expect(snmpCard.getByLabelText('Description 1')).toHaveValue('uptime')
    expect(snmpCard.getByLabelText('Description 2')).toHaveValue('system_description')
  })

  it('warns when the OIDs were saved but Nagios was not updated', async () => {
    await renderLoaded()
    savePluginSettings.mockResolvedValue({ ...snmp({ version: 1 }), config_ok: false, config_applied: false, config_message: 'Config failed to validate' })

    fireEvent.change(within(card('SNMP OIDs')).getByLabelText('OID 2'), { target: { value: '1.3.6.1.2.1.1.5.0' } })
    save('SNMP OIDs')

    expect(await screen.findByText(/OIDs were saved but Nagios was not updated: Config failed to validate/)).toBeInTheDocument()
  })

  it('shows the server error when saving fails', async () => {
    await renderLoaded()
    savePluginSettings.mockRejectedValue(new ApiError('These settings were updated by someone else. Reload and try again.', 409))

    fireEvent.change(within(card('SNMP OIDs')).getByLabelText('OID 2'), { target: { value: '1.3.6.1.2.1.1.5.0' } })
    save('SNMP OIDs')

    expect(await screen.findByText(/updated by someone else/)).toBeInTheDocument()
  })

  it('shows an error when loading fails', async () => {
    getPluginSettings.mockRejectedValue(new ApiError('Forbidden', 403))
    render(<PluginSettings />)

    expect(await screen.findByText('Forbidden')).toBeInTheDocument()
  })
})

describe('PluginSettings: NCPA', () => {
  beforeEach(() => {
    getPluginSettings.mockReset()
    savePluginSettings.mockReset()
  })

  it('adds the two bandwidth rows from a connection name and saves them', async () => {
    await renderLoaded({ version: 2 })
    const ncpaCard = within(card('NCPA Metrics'))
    savePluginSettings.mockResolvedValue({ ...ncpa({ version: 3 }), config_ok: true, config_applied: true, config_message: 'ok' })

    fireEvent.change(ncpaCard.getByLabelText('Network connection name'), { target: { value: 'ens18' } })
    fireEvent.click(ncpaCard.getByRole('button', { name: /add bandwidth rows/i }))

    expect(ncpaCard.getByDisplayValue('interface/ens18/bytes_recv')).toBeInTheDocument()
    expect(ncpaCard.getByDisplayValue('interface/ens18/bytes_sent')).toBeInTheDocument()
    save('NCPA Metrics')
    await waitFor(() => expect(savePluginSettings).toHaveBeenCalled())
    const sent = savePluginSettings.mock.calls[0][2] as { metric: string; path: string; queryargs: string }[]
    expect(sent.filter((r) => r.metric.startsWith('bandwidth_')).map((r) => [r.metric, r.path, r.queryargs])).toEqual([
      ['bandwidth_in', 'interface/ens18/bytes_recv', 'delta=1'],
      ['bandwidth_out', 'interface/ens18/bytes_sent', 'delta=1'],
    ])
  })

  it('rejects an invalid connection name', async () => {
    await renderLoaded()
    const ncpaCard = within(card('NCPA Metrics'))
    fireEvent.change(ncpaCard.getByLabelText('Network connection name'), { target: { value: 'bad name!' } })
    fireEvent.click(ncpaCard.getByRole('button', { name: /add bandwidth rows/i }))
    expect(ncpaCard.getByText(/Enter the connection name/)).toBeInTheDocument()
  })

  it('shows the metric table with every column and blanks for unset options', async () => {
    await renderLoaded()
    const ncpaCard = within(card('NCPA Metrics'))

    expect(ncpaCard.getByLabelText('Description 1')).toHaveValue('cpu')
    expect(ncpaCard.getByLabelText('Metric path 1')).toHaveValue('cpu/percent')
    expect(ncpaCard.getByLabelText('Warning 1')).toHaveValue('50')
    expect(ncpaCard.getByLabelText('Critical 1')).toHaveValue('80')
    expect(ncpaCard.getByLabelText('Query args 1')).toHaveValue('aggregate=avg')
    expect(ncpaCard.getByLabelText('Units 2')).toHaveValue('')
    expect(ncpaCard.getByText(/\{partition\} becomes one service per disk partition/)).toBeInTheDocument()
  })

  it('hides only the NCPA table until check_ncpa is installed', async () => {
    await renderLoaded({}, { installed: false, status: null })

    expect(screen.getByText('SNMP OIDs')).toBeInTheDocument()
    expect(screen.queryByText('NCPA Metrics')).not.toBeInTheDocument()
    expect(screen.getByText(/NCPA Metrics table appears here once check_ncpa is installed/)).toBeInTheDocument()
  })

  it('edits a threshold and saves the metrics, keeping empty options empty', async () => {
    await renderLoaded({}, { version: 2 })
    savePluginSettings.mockResolvedValue({ ...ncpa({ version: 3 }), config_ok: true, config_applied: true, config_message: 'ok' })

    fireEvent.change(within(card('NCPA Metrics')).getByLabelText('Critical 2'), { target: { value: '90' } })
    save('NCPA Metrics')

    await waitFor(() => expect(savePluginSettings).toHaveBeenCalledWith('ncpa', 'metrics', [
      { metric: 'cpu', path: 'cpu/percent', warning: '50', critical: '80', units: '', queryargs: 'aggregate=avg' },
      { metric: 'disk', path: 'disk/logical/{partition}/used_percent', warning: '70', critical: '90', units: '', queryargs: '' },
    ], 2))
  })

  it('does not save a bad path or threshold', async () => {
    await renderLoaded()
    const ncpaCard = within(card('NCPA Metrics'))

    fireEvent.change(ncpaCard.getByLabelText('Metric path 1'), { target: { value: 'cpu percent' } })
    save('NCPA Metrics')
    expect(ncpaCard.getByText(/Path for "cpu" must be an NCPA path/)).toBeInTheDocument()

    fireEvent.change(ncpaCard.getByLabelText('Metric path 1'), { target: { value: 'cpu/percent' } })
    fireEvent.change(ncpaCard.getByLabelText('Warning 1'), { target: { value: 'high' } })
    save('NCPA Metrics')
    expect(ncpaCard.getByText(/Warning for "cpu" must be a Nagios threshold/)).toBeInTheDocument()
    expect(savePluginSettings).not.toHaveBeenCalled()
  })

  it('resets only the NCPA table to its defaults, and saves them', async () => {
    const custom = [{ metric: 'load', path: 'cpu/percent', warning: '60', critical: '90' }]
    await renderLoaded({}, { settings: { metrics: custom }, version: 1 })
    const ncpaCard = within(card('NCPA Metrics'))
    fireEvent.change(within(card('SNMP OIDs')).getByLabelText('OID 1'), { target: { value: '1.3.6.1.2.1.1.5.0' } })
    savePluginSettings.mockResolvedValue({ ...ncpa({ version: 2 }), config_ok: true, config_applied: true, config_message: 'ok' })

    fireEvent.click(ncpaCard.getByRole('button', { name: /reset to defaults/i }))

    expect(ncpaCard.getByLabelText('Description 1')).toHaveValue('cpu')
    expect(ncpaCard.getByLabelText('Query args 1')).toHaveValue('aggregate=avg')
    expect(ncpaCard.getByLabelText('Description 2')).toHaveValue('disk')
    expect(ncpaCard.getByLabelText('Critical 2')).toHaveValue('95')
    expect(ncpaCard.queryByDisplayValue('load')).not.toBeInTheDocument()
    expect(within(card('SNMP OIDs')).getByLabelText('OID 1')).toHaveValue('1.3.6.1.2.1.1.5.0')

    save('NCPA Metrics')

    await waitFor(() => expect(savePluginSettings).toHaveBeenCalledWith('ncpa', 'metrics', [
      { metric: 'cpu', path: 'cpu/percent', warning: '50', critical: '80', units: '', queryargs: 'aggregate=avg' },
      { metric: 'disk', path: 'disk/logical/{partition}/used_percent', warning: '70', critical: '95', units: '', queryargs: '' },
    ], 1))
  })

  it('discards a reset that was not saved', async () => {
    const custom = [{ metric: 'load', path: 'cpu/percent' }]
    await renderLoaded({}, { settings: { metrics: custom } })
    const ncpaCard = within(card('NCPA Metrics'))

    fireEvent.click(ncpaCard.getByRole('button', { name: /reset to defaults/i }))
    fireEvent.click(ncpaCard.getByRole('button', { name: /discard changes/i }))

    expect(ncpaCard.getByLabelText('Description 1')).toHaveValue('load')
    expect(ncpaCard.queryByLabelText('Description 2')).not.toBeInTheDocument()
    expect(savePluginSettings).not.toHaveBeenCalled()
  })

  it('saves NCPA without touching the SNMP table', async () => {
    await renderLoaded()
    savePluginSettings.mockResolvedValue({ ...ncpa({ version: 1 }), config_ok: true, config_applied: true, config_message: 'ok' })

    fireEvent.change(within(card('SNMP OIDs')).getByLabelText('OID 1'), { target: { value: '1.3.6.1.2.1.1.5.0' } })
    fireEvent.change(within(card('NCPA Metrics')).getByLabelText('Units 1'), { target: { value: '%' } })
    save('NCPA Metrics')

    await waitFor(() => expect(savePluginSettings).toHaveBeenCalledTimes(1))
    expect(savePluginSettings.mock.calls[0][0]).toBe('ncpa')
    expect(within(card('SNMP OIDs')).getByLabelText('OID 1')).toHaveValue('1.3.6.1.2.1.1.5.0')
  })
})
