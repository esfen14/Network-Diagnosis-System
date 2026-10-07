import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { PluginCustomChecksSection } from '../components/plugin-manager/PluginCustomChecksSection'
import type { CustomCheckField, CustomCheckItem, CustomChecksResponse } from '../types/plugin'

const api = vi.hoisted(() => ({
  getCustomChecks: vi.fn(),
  searchCustomCheckDevices: vi.fn(),
  addCustomCheck: vi.fn(),
  changeCustomCheck: vi.fn(),
  pauseCustomCheck: vi.fn(),
  resumeCustomCheck: vi.fn(),
  removeCustomCheck: vi.fn(),
}))
vi.mock('../lib/pluginApi', () => api)

const FIELDS: CustomCheckField[] = [
  { name: 'ups', flag: '-u', label: 'UPS name', required: true, placeholder: '' },
  { name: 'warning', flag: '-w', label: 'Warning battery level (%)', required: false, placeholder: '' },
]

function check(overrides: Partial<CustomCheckItem> = {}): CustomCheckItem {
  return {
    id: 12,
    name: 'Rack UPS',
    service: 'custom-ups-rack_ups',
    device: { id: 4, hostname: 'rack-01', ip_address: '10.0.0.5' },
    variables: { ups: 'nut1', warning: '50' },
    paused: false,
    running_since: '2026-10-07T09:30:00+00:00',
    status: { kind: 'ok', state: 'OK', output: 'UPS OK - battery 100%', last_check: '2026-10-07T09:35:00+00:00' },
    ...overrides,
  }
}

function response(items: CustomCheckItem[]): CustomChecksResponse {
  return { items, page: 1, per_page: 5, pages: 1, total: items.length, has_next: false, has_prev: false }
}

function renderSection(onChanged = vi.fn()) {
  return render(<PluginCustomChecksSection pluginId={3} pluginName="check_ups" fields={FIELDS} onChanged={onChanged} />)
}

// Fill the dialog far enough that Add check is allowed.
async function fillDialog(dialog: HTMLElement, upsName = 'nut1') {
  fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'x' } })
  fireEvent.change(within(dialog).getByLabelText(/UPS name/), { target: { value: upsName } })
  fireEvent.click(await within(dialog).findByRole('button', { name: /rack-01/ }))
}

describe('PluginCustomChecksSection', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getCustomChecks.mockResolvedValue(response([check()]))
    api.searchCustomCheckDevices.mockResolvedValue([
      { id: 4, hostname: 'rack-01', ip_address: '10.0.0.5' },
      { id: 5, hostname: 'web-01', ip_address: '10.0.0.6' },
    ])
  })

  it('lists a check with its device, arguments, status and output', async () => {
    renderSection()

    expect(await screen.findByText('Rack UPS')).toBeInTheDocument()
    expect(screen.getByText(/rack-01 · 10\.0\.0\.5/)).toBeInTheDocument()
    expect(screen.getByText('-u nut1 -w 50')).toBeInTheDocument()
    expect(screen.getByText('OK')).toBeInTheDocument()
    expect(screen.getByText('UPS OK - battery 100%')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 1 · 1 check')).toBeInTheDocument()
    expect(api.getCustomChecks).toHaveBeenCalledWith(3, { page: 1, per_page: 5, search: '' })
  })

  it('says what to do when there are no checks', async () => {
    api.getCustomChecks.mockResolvedValue(response([]))
    renderSection()

    expect(await screen.findByText(/No checks yet\. Add one to run this plugin against a device\./)).toBeInTheDocument()
  })

  it('shows a paused check as paused with a Resume button', async () => {
    api.getCustomChecks.mockResolvedValue(
      response([check({ paused: true, running_since: null, status: { kind: 'paused', state: null, output: 'Paused.', last_check: null } })]),
    )
    renderSection()

    expect(await screen.findByRole('button', { name: 'Resume Rack UPS on rack-01' })).toBeInTheDocument()
    expect(screen.getByText('Paused.')).toBeInTheDocument()
  })

  it('adds a check on the chosen device with the typed arguments', async () => {
    api.addCustomCheck.mockResolvedValue({ ...check({ id: 13, name: 'Spare UPS' }), changed: true, message: '' })
    const onChanged = vi.fn()
    renderSection(onChanged)
    await screen.findByText('Rack UPS')

    fireEvent.click(screen.getByRole('button', { name: /Add check/ }))
    const dialog = await screen.findByRole('dialog', { name: 'Add a check_ups check' })
    const addButton = within(dialog).getByRole('button', { name: 'Add check' })
    expect(addButton).toBeDisabled()

    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: ' Spare UPS ' } })
    fireEvent.change(within(dialog).getByLabelText(/UPS name/), { target: { value: 'nut2' } })
    fireEvent.click(await within(dialog).findByRole('button', { name: /web-01 · 10\.0\.0\.6/ }))
    expect(addButton).toBeEnabled()
    fireEvent.click(addButton)

    await waitFor(() =>
      expect(api.addCustomCheck).toHaveBeenCalledWith(3, { device_id: 5, name: 'Spare UPS', variables: { ups: 'nut2' } }),
    )
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('does not let a required argument stay empty or an unsafe character through', async () => {
    renderSection()
    await screen.findByText('Rack UPS')
    fireEvent.click(screen.getByRole('button', { name: /Add check/ }))
    const dialog = await screen.findByRole('dialog')

    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'x' } })
    fireEvent.click(await within(dialog).findByRole('button', { name: /rack-01/ }))
    expect(within(dialog).getByRole('button', { name: 'Add check' })).toBeDisabled() // UPS name is empty

    fireEvent.change(within(dialog).getByLabelText(/UPS name/), { target: { value: "a'b" } })
    expect(within(dialog).getByRole('button', { name: 'Add check' })).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText(/UPS name/), { target: { value: 'nut1' } })
    expect(within(dialog).getByRole('button', { name: 'Add check' })).toBeEnabled()
  })

  it('shows the server message and keeps the dialog open when Nagios refuses', async () => {
    api.addCustomCheck.mockRejectedValue(new ApiError('Nagios did not accept the change, so nothing was changed: bad', 409))
    renderSection()
    await screen.findByText('Rack UPS')
    fireEvent.click(screen.getByRole('button', { name: /Add check/ }))
    const dialog = await screen.findByRole('dialog')
    await fillDialog(dialog)
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add check' }))

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('nothing was changed: bad')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('changes a check without offering to move it to another device', async () => {
    api.changeCustomCheck.mockResolvedValue({ ...check({ name: 'Server room UPS' }), changed: true, message: '' })
    renderSection()
    fireEvent.click(await screen.findByRole('button', { name: 'Change Rack UPS on rack-01' }))

    const dialog = await screen.findByRole('dialog', { name: 'Change Rack UPS' })
    expect(within(dialog).queryByLabelText('Device')).not.toBeInTheDocument()
    expect(within(dialog).getByText(/remove this check and add\s+a new one/)).toBeInTheDocument()
    expect(api.searchCustomCheckDevices).not.toHaveBeenCalled()
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'Server room UPS' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(api.changeCustomCheck).toHaveBeenCalledWith(3, 12, { name: 'Server room UPS', variables: { ups: 'nut1', warning: '50' } }),
    )
  })

  it('pauses and removes a check', async () => {
    api.pauseCustomCheck.mockResolvedValue({})
    api.removeCustomCheck.mockResolvedValue({ id: 12, changed: true, message: '' })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection()

    fireEvent.click(await screen.findByRole('button', { name: 'Pause Rack UPS on rack-01' }))
    await waitFor(() => expect(api.pauseCustomCheck).toHaveBeenCalledWith(3, 12))

    fireEvent.click(screen.getByRole('button', { name: 'Remove Rack UPS from rack-01' }))
    await waitFor(() => expect(api.removeCustomCheck).toHaveBeenCalledWith(3, 12))
    expect(confirm).toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('resumes a paused check', async () => {
    api.getCustomChecks.mockResolvedValue(
      response([check({ paused: true, running_since: null, status: { kind: 'paused', state: null, output: 'Paused.', last_check: null } })]),
    )
    api.resumeCustomCheck.mockResolvedValue({})
    renderSection()

    fireEvent.click(await screen.findByRole('button', { name: 'Resume Rack UPS on rack-01' }))
    await waitFor(() => expect(api.resumeCustomCheck).toHaveBeenCalledWith(3, 12))
  })

  it('removes nothing when the confirmation is declined', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderSection()

    fireEvent.click(await screen.findByRole('button', { name: 'Remove Rack UPS from rack-01' }))
    expect(api.removeCustomCheck).not.toHaveBeenCalled()
    confirm.mockRestore()
  })

  it('shows the error when a check cannot be paused', async () => {
    api.pauseCustomCheck.mockRejectedValue(new ApiError('Nagios did not accept the change', 409))
    renderSection()

    fireEvent.click(await screen.findByRole('button', { name: 'Pause Rack UPS on rack-01' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Nagios did not accept the change')
  })
})

describe('PluginCustomChecksSection with passwords', () => {
  const FIELDS_WITH_PASSWORD: CustomCheckField[] = [
    { name: 'user', flag: '-u', label: 'Username to test with', required: true, placeholder: '' },
    { name: 'password', flag: '-p', label: 'Password to test with', required: true, placeholder: '', secret: true },
    { name: 'note', flag: '-n', label: 'Optional token', required: false, placeholder: '', secret: true },
  ]
  const stored = (overrides: Partial<CustomCheckItem> = {}) =>
    check({
      name: 'Auth probe',
      variables: { user: 'probe' },
      secrets_set: ['password', 'note'],
      secrets_readable: true,
      ...overrides,
    })

  function renderWithPasswords() {
    return render(
      <PluginCustomChecksSection pluginId={9} pluginName="check_radius" fields={FIELDS_WITH_PASSWORD} onChanged={vi.fn()} />,
    )
  }

  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getCustomChecks.mockResolvedValue(response([stored()]))
    api.searchCustomCheckDevices.mockResolvedValue([{ id: 4, hostname: 'rack-01', ip_address: '10.0.0.5' }])
  })

  it('shows a stored password as dots, never its value', async () => {
    renderWithPasswords()

    expect(await screen.findByText('-u probe  -p ••••••  -n ••••••'.replace(/  /g, ' '))).toBeInTheDocument()
  })

  it('masks the field, warns about where the password goes, and requires it when adding', async () => {
    renderWithPasswords()
    await screen.findByText('Auth probe')
    fireEvent.click(screen.getByRole('button', { name: /Add check/ }))
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getByLabelText(/Password to test with/)).toHaveAttribute('type', 'password')
    expect(within(dialog).getByLabelText(/Username to test with/)).toHaveAttribute('type', 'text')
    expect(within(dialog).getByText(/stored encrypted and are never shown again/)).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'x' } })
    fireEvent.change(within(dialog).getByLabelText(/Username to test with/), { target: { value: 'probe' } })
    fireEvent.click(await within(dialog).findByRole('button', { name: /rack-01/ }))
    expect(within(dialog).getByRole('button', { name: 'Add check' })).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText(/Password to test with/), { target: { value: 'S3cret' } })
    expect(within(dialog).getByRole('button', { name: 'Add check' })).toBeEnabled()
  })

  it('sends the typed password with the add request', async () => {
    api.addCustomCheck.mockResolvedValue({ ...stored(), changed: true, message: '' })
    renderWithPasswords()
    await screen.findByText('Auth probe')
    fireEvent.click(screen.getByRole('button', { name: /Add check/ }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'New probe' } })
    fireEvent.change(within(dialog).getByLabelText(/Username to test with/), { target: { value: 'probe' } })
    fireEvent.change(within(dialog).getByLabelText(/Password to test with/), { target: { value: 'S3cret' } })
    fireEvent.click(await within(dialog).findByRole('button', { name: /rack-01/ }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Add check' }))

    await waitFor(() =>
      expect(api.addCustomCheck).toHaveBeenCalledWith(9, {
        device_id: 4, name: 'New probe', variables: { user: 'probe', password: 'S3cret' },
      }),
    )
  })

  it('keeps a stored password when it is left blank on a change', async () => {
    api.changeCustomCheck.mockResolvedValue({ ...stored(), changed: true, message: '' })
    renderWithPasswords()
    fireEvent.click(await screen.findByRole('button', { name: 'Change Auth probe on rack-01' }))
    const dialog = await screen.findByRole('dialog', { name: 'Change Auth probe' })

    const password = within(dialog).getByLabelText(/Password to test with/)
    expect(password).toHaveValue('')
    expect(password).toHaveAttribute('placeholder', 'Stored. Leave blank to keep it')
    const save = within(dialog).getByRole('button', { name: 'Save changes' })
    expect(save).toBeEnabled() // the required password is already stored
    fireEvent.click(save)

    await waitFor(() => expect(api.changeCustomCheck).toHaveBeenCalledWith(9, 12, { name: 'Auth probe', variables: { user: 'probe' } }))
  })

  it('sends a new password to replace the stored one', async () => {
    api.changeCustomCheck.mockResolvedValue({ ...stored(), changed: true, message: '' })
    renderWithPasswords()
    fireEvent.click(await screen.findByRole('button', { name: 'Change Auth probe on rack-01' }))
    const dialog = await screen.findByRole('dialog')
    fireEvent.change(within(dialog).getByLabelText(/Password to test with/), { target: { value: 'N3w' } })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(api.changeCustomCheck).toHaveBeenCalledWith(9, 12, { name: 'Auth probe', variables: { user: 'probe', password: 'N3w' } }),
    )
  })

  it('offers to remove an optional stored password and never a required one', async () => {
    api.changeCustomCheck.mockResolvedValue({ ...stored(), changed: true, message: '' })
    renderWithPasswords()
    fireEvent.click(await screen.findByRole('button', { name: 'Change Auth probe on rack-01' }))
    const dialog = await screen.findByRole('dialog')

    expect(within(dialog).getAllByRole('checkbox')).toHaveLength(1)
    fireEvent.click(within(dialog).getByRole('checkbox', { name: /Remove the stored optional token/ }))
    expect(within(dialog).getByLabelText(/Optional token/)).toHaveAttribute('placeholder', '')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    await waitFor(() =>
      expect(api.changeCustomCheck).toHaveBeenCalledWith(9, 12, {
        name: 'Auth probe', variables: { user: 'probe' }, clear_secrets: ['note'],
      }),
    )
  })

  it('says when a stored password can no longer be read and asks for it again', async () => {
    api.getCustomChecks.mockResolvedValue(response([stored({ secrets_readable: false })]))
    renderWithPasswords()

    expect(await screen.findByText(/A stored password can no longer be read, so this check is not running/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Change Auth probe on rack-01' }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText(/The stored password can no longer be read \(the server key changed\)/)).toBeInTheDocument()
  })
})
