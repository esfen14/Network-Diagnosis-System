import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PluginSettings } from '../components/settings/PluginSettings'
import { ApiError } from '../lib/api'

const getPluginSettings = vi.fn()
const saveSnmpSettings = vi.fn()

vi.mock('../lib/pluginSettingsApi', () => ({
  getPluginSettings: () => getPluginSettings(),
  saveSnmpSettings: (...args: unknown[]) => saveSnmpSettings(...args),
}))

const OIDS = [
  { metric: 'uptime', oid: '1.3.6.1.2.1.1.3.0' },
  { metric: 'system_description', oid: '1.3.6.1.2.1.1.1.0' },
]

function section(overrides: Record<string, unknown> = {}) {
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

async function renderLoaded(overrides: Record<string, unknown> = {}) {
  getPluginSettings.mockResolvedValue({ snmp: section(overrides) })
  render(<PluginSettings />)
  await waitFor(() => expect(screen.queryByText(/Loading plugin settings/)).not.toBeInTheDocument())
}

function save() {
  fireEvent.click(screen.getByRole('button', { name: /save changes/i }))
}

describe('PluginSettings', () => {
  beforeEach(() => {
    getPluginSettings.mockReset()
    saveSnmpSettings.mockReset()
  })

  it('shows the OID table with each description and OID', async () => {
    await renderLoaded()

    expect(screen.getByText('SNMP OIDs')).toBeInTheDocument()
    expect(screen.getByLabelText('Description 1')).toHaveValue('uptime')
    expect(screen.getByLabelText('OID 1')).toHaveValue('1.3.6.1.2.1.1.3.0')
    expect(screen.getByLabelText('Description 2')).toHaveValue('system_description')
  })

  it('hides the table until check_snmp is installed', async () => {
    await renderLoaded({ installed: false, status: null })

    expect(screen.queryByText('SNMP OIDs')).not.toBeInTheDocument()
    expect(screen.getByText(/appears here once check_snmp is installed/)).toBeInTheDocument()
  })

  it('warns when check_snmp is installed but not enabled', async () => {
    await renderLoaded({ status: 'Ready' })

    expect(screen.getByText(/check_snmp is Ready/)).toBeInTheDocument()
  })

  it('changes an OID in place and saves the table with its version', async () => {
    await renderLoaded({ version: 3 })
    const changed = [{ metric: 'uptime', oid: '1.3.6.1.2.1.25.1.1.0' }, OIDS[1]]
    saveSnmpSettings.mockResolvedValue({ ...section({ settings: { oids: changed }, version: 4 }), config_ok: true, config_applied: true, config_message: 'ok' })

    fireEvent.change(screen.getByLabelText('OID 1'), { target: { value: '1.3.6.1.2.1.25.1.1.0' } })
    save()

    await waitFor(() => expect(saveSnmpSettings).toHaveBeenCalledWith(changed, 3))
    await waitFor(() => expect(screen.getByLabelText('OID 1')).toHaveValue('1.3.6.1.2.1.25.1.1.0'))
  })

  it('adds and removes rows, and warns that a new description makes a new service', async () => {
    await renderLoaded()

    fireEvent.change(screen.getByLabelText('New OID description'), { target: { value: 'CPU_Load' } })
    fireEvent.change(screen.getByLabelText('New OID'), { target: { value: '1.3.6.1.4.1.2021.10.1.3.1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add OID' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove system_description' }))

    expect(screen.getByLabelText('Description 2')).toHaveValue('cpu_load')
    expect(screen.queryByDisplayValue('system_description')).not.toBeInTheDocument()
    expect(screen.getByText(/creates a new Nagios service/)).toBeInTheDocument()
  })

  it('refuses an invalid new row', async () => {
    await renderLoaded()

    fireEvent.change(screen.getByLabelText('New OID description'), { target: { value: 'uptime' } })
    fireEvent.change(screen.getByLabelText('New OID'), { target: { value: '1.3.6.1.9' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add OID' }))

    expect(screen.getByText('Description "uptime" is used more than once.')).toBeInTheDocument()
  })

  it('does not save a table with a bad OID', async () => {
    await renderLoaded()

    fireEvent.change(screen.getByLabelText('OID 1'), { target: { value: '1.3.six' } })
    save()

    expect(screen.getByText(/OID for "uptime" must be numeric and dotted/)).toBeInTheDocument()
    expect(saveSnmpSettings).not.toHaveBeenCalled()
  })

  it('resets to the config.py defaults', async () => {
    await renderLoaded({ settings: { oids: [{ metric: 'custom', oid: '1.3.6.1.1' }] } })

    fireEvent.click(screen.getByRole('button', { name: /reset to defaults/i }))

    expect(screen.getByLabelText('Description 1')).toHaveValue('uptime')
    expect(screen.getByLabelText('Description 2')).toHaveValue('system_description')
  })

  it('warns when the OIDs were saved but Nagios was not updated', async () => {
    await renderLoaded()
    saveSnmpSettings.mockResolvedValue({ ...section({ version: 1 }), config_ok: false, config_applied: false, config_message: 'Config failed to validate' })

    fireEvent.change(screen.getByLabelText('OID 2'), { target: { value: '1.3.6.1.2.1.1.5.0' } })
    save()

    expect(await screen.findByText(/saved but Nagios was not updated: Config failed to validate/)).toBeInTheDocument()
  })

  it('shows the server error when saving fails', async () => {
    await renderLoaded()
    saveSnmpSettings.mockRejectedValue(new ApiError('SNMP settings were updated by someone else. Reload and try again.', 409))

    fireEvent.change(screen.getByLabelText('OID 2'), { target: { value: '1.3.6.1.2.1.1.5.0' } })
    save()

    expect(await screen.findByText(/updated by someone else/)).toBeInTheDocument()
  })

  it('shows an error when loading fails', async () => {
    getPluginSettings.mockRejectedValue(new ApiError('Forbidden', 403))
    render(<PluginSettings />)

    expect(await screen.findByText('Forbidden')).toBeInTheDocument()
  })
})
