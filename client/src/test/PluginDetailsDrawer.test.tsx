import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ApiError } from '../lib/api'
import { PluginDetailsDrawer } from '../components/plugin-manager/PluginDetailsDrawer'
import type { EnablePreview, PluginDetails } from '../types/plugin'

const api = vi.hoisted(() => ({
  getPluginDetails: vi.fn(),
  getPluginCommands: vi.fn(),
  getPluginDependencies: vi.fn(),
  getEnablePreview: vi.fn(),
  enablePlugin: vi.fn(),
  disablePlugin: vi.fn(),
  validatePlugin: vi.fn(),
  overrideCommand: vi.fn(),
  restoreDefaultCommand: vi.fn(),
  updatePlugin: vi.fn(),
  rollbackPluginUpdate: vi.fn(),
}))

vi.mock('../lib/pluginApi', () => api)

const permissions = vi.hoisted(() => ({ denied: new Set<string>() }))
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({ user: null, isLoading: false, hasPermission: (name: string) => !permissions.denied.has(name) }),
}))

// The custom checks list has its own tests; here it only shows that it was rendered.
vi.mock('../components/plugin-manager/PluginCustomChecksSection', () => ({
  PluginCustomChecksSection: ({ pluginName }: { pluginName: string }) => <div>custom checks of {pluginName}</div>,
}))

// The list has its own tests; here it only shows that it was rendered and when it reloads.
vi.mock('../components/plugin-manager/PluginServicesSection', () => ({
  PluginServicesSection: ({ pluginId, refreshKey }: { pluginId: number; refreshKey: number }) => (
    <div>Services section for {pluginId} (reload {refreshKey})</div>
  ),
}))

function details(overrides: Partial<PluginDetails> = {}): PluginDetails {
  return {
    id: 1,
    name: 'check_ssh',
    display_name: null,
    description: 'Check SSH server connection.',
    author: null,
    category: 'Network Services',
    documentation_url: 'https://www.nagios-plugins.org/doc/man/check_ssh.html',
    service_driven: true,
    type: 'Nagios',
    source: 'Baseline (ISO)',
    status: 'Ready',
    current_version: '2.4.12',
    executable_path: '/usr/local/nagios/libexec/check_ssh',
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
    commands_count: 1,
    dependencies_count: 0,
    monitoring_usage: { services: 0, devices: 0, placeholder: false, note: '' },
    ...overrides,
  }
}

function preview(overrides: Partial<EnablePreview> = {}): EnablePreview {
  return {
    id: 1, name: 'check_ssh', status: 'Ready', service_driven: true, already_enabled: false,
    matched_services: 12, matched_devices: 5, held_ports: 0, message: 'Enabling will monitor 12 service(s) on 5 device(s).',
    ...overrides,
  }
}

const attach = (overrides = {}) => ({
  success: true, changed: true, applied: 12, removed: 0, promoted: 12, message: 'applied', ...overrides,
})

function renderDrawer(onChanged = vi.fn()) {
  return render(<PluginDetailsDrawer pluginId={1} onClose={() => {}} onChanged={onChanged} />)
}

describe('PluginDetailsDrawer description', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getPluginCommands.mockResolvedValue([])
    api.getPluginDependencies.mockResolvedValue([])
  })

  it('shows the description, category and a documentation link', async () => {
    api.getPluginDetails.mockResolvedValue(details())
    renderDrawer()

    expect(await screen.findByText('Check SSH server connection.')).toBeInTheDocument()
    expect(screen.getByText('Network Services')).toBeInTheDocument()

    const link = screen.getByRole('link', { name: 'Documentation' })
    expect(link).toHaveAttribute('href', 'https://www.nagios-plugins.org/doc/man/check_ssh.html')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('falls back to a message and no link for a plugin without a description', async () => {
    api.getPluginDetails.mockResolvedValue(
      details({ name: 'check_company', description: null, category: null, documentation_url: null }),
    )
    renderDrawer()

    expect(await screen.findByText('No description available.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Documentation' })).not.toBeInTheDocument()
  })
})

describe('PluginDetailsDrawer enable and disable', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getPluginCommands.mockResolvedValue([])
    api.getPluginDependencies.mockResolvedValue([])
    api.getPluginDetails.mockResolvedValue(details())
  })

  it('no longer offers to pick a device by hand', async () => {
    renderDrawer()

    await screen.findByText('Check SSH server connection.')
    expect(screen.queryByText(/apply to device/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('lists the services a service-driven plugin monitors', async () => {
    renderDrawer()

    expect(await screen.findByText('Services section for 1 (reload 0)')).toBeInTheDocument()
  })

  it('shows what enabling would monitor and waits for confirmation', async () => {
    api.getEnablePreview.mockResolvedValue(preview())
    renderDrawer()

    fireEvent.click(await screen.findByRole('button', { name: /^Enable$/ }))

    const dialog = await screen.findByRole('dialog', { name: 'Enable check_ssh' })
    expect(within(dialog).getByText('Enabling will monitor 12 service(s) on 5 device(s).')).toBeInTheDocument()
    expect(within(dialog).getByText('12')).toBeInTheDocument()
    expect(within(dialog).getByText('5')).toBeInTheDocument()
    expect(within(dialog).getByText(/not picked by hand/)).toBeInTheDocument()
    expect(api.enablePlugin).not.toHaveBeenCalled()
  })

  it('tells the admin how many identified ports are held back and will not be attached', async () => {
    api.getEnablePreview.mockResolvedValue(preview({
      held_ports: 3,
      message: 'Enabling will monitor 12 service(s) on 5 device(s). 3 identified port(s) are held back '
        + '(left Suggested on purpose or at an upgrade) and will not be attached until an admin monitors them.',
    }))
    renderDrawer()

    fireEvent.click(await screen.findByRole('button', { name: /^Enable$/ }))

    const dialog = await screen.findByRole('dialog', { name: 'Enable check_ssh' })
    expect(within(dialog).getByText(/3 identified port\(s\) are held back/)).toBeInTheDocument()
    expect(within(dialog).getByText(/will not be attached until an admin monitors them/)).toBeInTheDocument()
    expect(within(dialog).getByText("Monitor them from each device's Ports list.")).toBeInTheDocument()
  })

  it('has no Ports hint when nothing is held back', async () => {
    api.getEnablePreview.mockResolvedValue(preview({ held_ports: 0 }))
    renderDrawer()

    fireEvent.click(await screen.findByRole('button', { name: /^Enable$/ }))

    const dialog = await screen.findByRole('dialog', { name: 'Enable check_ssh' })
    expect(within(dialog).queryByText(/Ports list/)).not.toBeInTheDocument()
  })

  it('does not enable when the preview is cancelled', async () => {
    api.getEnablePreview.mockResolvedValue(preview())
    renderDrawer()

    fireEvent.click(await screen.findByRole('button', { name: /^Enable$/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(api.enablePlugin).not.toHaveBeenCalled()
  })

  it('enables after confirmation, reloads the list and tells the page', async () => {
    api.getEnablePreview.mockResolvedValue(preview())
    api.enablePlugin.mockResolvedValue({ id: 1, status: 'Active', changed: true, auto_apply: attach() })
    const onChanged = vi.fn()
    renderDrawer(onChanged)

    fireEvent.click(await screen.findByRole('button', { name: /^Enable$/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm enable' }))

    expect(await screen.findByText('Monitoring 12 new service(s) from discovered ports.')).toBeInTheDocument()
    expect(api.enablePlugin).toHaveBeenCalledWith(1)
    expect(onChanged).toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText('Services section for 1 (reload 1)')).toBeInTheDocument()
  })

  it('says so when nothing matched yet', async () => {
    api.getEnablePreview.mockResolvedValue(preview({ matched_services: 0, matched_devices: 0, message: 'No matching services yet.' }))
    api.enablePlugin.mockResolvedValue({ id: 1, status: 'Enabled', changed: true, auto_apply: attach({ applied: 0, promoted: 0 }) })
    renderDrawer()

    fireEvent.click(await screen.findByRole('button', { name: /^Enable$/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByText('Devices')).not.toBeInTheDocument()
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm enable' }))

    expect(await screen.findByText(/No matching services yet; they attach as devices are found/)).toBeInTheDocument()
  })

  it('warns when the plugin was enabled but Nagios was not updated', async () => {
    api.getEnablePreview.mockResolvedValue(preview())
    api.enablePlugin.mockResolvedValue({
      id: 1, status: 'Enabled', changed: true,
      auto_apply: attach({ success: false, applied: 0, message: 'Config failed to validate: bad directive' }),
    })
    renderDrawer()

    fireEvent.click(await screen.findByRole('button', { name: /^Enable$/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm enable' }))

    expect(await screen.findByText(/Nagios was not updated: Config failed to validate: bad directive/)).toBeInTheDocument()
  })

  it('shows the server message when the preview cannot be loaded', async () => {
    api.getEnablePreview.mockRejectedValue(new ApiError('Plugin not found.', 404))
    renderDrawer()

    fireEvent.click(await screen.findByRole('button', { name: /^Enable$/ }))

    expect(await screen.findByText('Plugin not found.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('reports how many services a disable stopped', async () => {
    api.getPluginDetails.mockResolvedValue(details({ status: 'Active' }))
    api.disablePlugin.mockResolvedValue({
      id: 1, status: 'Disabled', changed: true, auto_apply: attach({ applied: 0, removed: 12 }),
    })
    renderDrawer()

    fireEvent.click(await screen.findByRole('button', { name: /^Disable$/ }))

    expect(await screen.findByText('Stopped 12 service(s). Enabling again restores them.')).toBeInTheDocument()
  })

  it('shows why Nagios refused a disable and that the plugin is still on', async () => {
    api.getPluginDetails.mockResolvedValue(details({ status: 'Active' }))
    api.disablePlugin.mockRejectedValue(
      new ApiError('Nagios did not accept the change, so the plugin is still on: bad directive', 409),
    )
    renderDrawer()

    fireEvent.click(await screen.findByRole('button', { name: /^Disable$/ }))

    expect(await screen.findByText(/the plugin is still on: bad directive/)).toBeInTheDocument()
  })

  it('cannot enable a plugin that is already on', async () => {
    api.getPluginDetails.mockResolvedValue(details({ status: 'Enabled' }))
    renderDrawer()

    expect(await screen.findByRole('button', { name: /^Enable$/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /^Disable$/ })).toBeEnabled()
  })
})

describe('PluginDetailsDrawer not service-driven', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getPluginCommands.mockResolvedValue([])
    api.getPluginDependencies.mockResolvedValue([])
  })

  it('explains that there is nothing to attach and offers no Enable, Disable or services list', async () => {
    api.getPluginDetails.mockResolvedValue(details({ name: 'check_ping', service_driven: false }))
    renderDrawer()

    expect(await screen.findByText('Not service-driven.')).toBeInTheDocument()
    expect(screen.getByText(/does not check a service that discovery finds on a port/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Enable$/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Disable$/ })).not.toBeInTheDocument()
    expect(screen.queryByText(/Services section/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Validate/ })).toBeInTheDocument()
  })

  it.each(['check_load', 'check_disk', 'check_swap', 'check_procs', 'check_users'])(
    'says %s is checked by Nagios Core itself',
    async (name) => {
      api.getPluginDetails.mockResolvedValue(details({ name, service_driven: false }))
      renderDrawer()

      expect(await screen.findByText(/Checks the Nagios server itself through Nagios Core. Not managed here./)).toBeInTheDocument()
    },
  )

  it('offers custom checks, and says why, for a plugin that takes them', async () => {
    api.getPluginDetails.mockResolvedValue(details({
      name: 'check_by_ssh', service_driven: false,
      custom_checks: { class: 'custom', supported: true, note: null, fields: [] },
    }))
    renderDrawer()

    expect(await screen.findByText(/Add a custom check to run it against a device/)).toBeInTheDocument()
    expect(screen.getByText('custom checks of check_by_ssh')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Enable$/ })).not.toBeInTheDocument()
  })

  it('hides the custom checks from someone without the permission', async () => {
    permissions.denied = new Set(['plugin.custom_check'])
    api.getPluginDetails.mockResolvedValue(details({
      name: 'check_by_ssh', service_driven: false,
      custom_checks: { class: 'custom', supported: true, note: null, fields: [] },
    }))
    renderDrawer()

    await screen.findByText('Not service-driven.')
    expect(screen.queryByText('custom checks of check_by_ssh')).not.toBeInTheDocument()
    permissions.denied = new Set()
  })

  it.each([
    ['check_apt', 'server', 'Runs on the Nagios server. Not available yet.'],
    ['check_cluster', 'unsupported', 'Aggregates other services. Not available yet.'],
    ['check_radius', 'credentials', 'Needs a password, which custom checks cannot store yet.'],
  ] as const)('explains why %s takes no custom check', async (name, plugin_class, note) => {
    api.getPluginDetails.mockResolvedValue(details({
      name, service_driven: false, custom_checks: { class: plugin_class, supported: false, note, fields: [] },
    }))
    renderDrawer()

    expect(await screen.findByText(note)).toBeInTheDocument()
    expect(screen.queryByText(/custom checks of/)).not.toBeInTheDocument()
  })

  it('still lets a plugin that was enabled before this rule be disabled', async () => {
    api.getPluginDetails.mockResolvedValue(details({ name: 'check_ping', service_driven: false, status: 'Active' }))
    renderDrawer()

    expect(await screen.findByRole('button', { name: /^Disable$/ })).toBeEnabled()
    expect(screen.queryByRole('button', { name: /^Enable$/ })).not.toBeInTheDocument()
  })

  it('does not ask for a preview', async () => {
    api.getPluginDetails.mockResolvedValue(details({ name: 'check_ping', service_driven: false }))
    renderDrawer()

    await screen.findByText('Not service-driven.')
    await waitFor(() => expect(api.getEnablePreview).not.toHaveBeenCalled())
  })
})
