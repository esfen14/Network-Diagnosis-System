import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { PluginDetailsDrawer } from '../components/plugin-manager/PluginDetailsDrawer'
import type { PluginDetails } from '../types/plugin'

const getPluginDetails = vi.fn()

vi.mock('../lib/pluginApi', () => ({
  getPluginDetails: (id: number) => getPluginDetails(id),
  getPluginCommands: () => Promise.resolve([]),
  getPluginDependencies: () => Promise.resolve([]),
  enablePlugin: vi.fn(),
  disablePlugin: vi.fn(),
  validatePlugin: vi.fn(),
  overrideCommand: vi.fn(),
  restoreDefaultCommand: vi.fn(),
  updatePlugin: vi.fn(),
  rollbackPluginUpdate: vi.fn(),
}))

vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({ user: null, isLoading: false, hasPermission: () => true }),
}))

vi.mock('../components/plugin-manager/PluginTargetsSection', () => ({
  PluginTargetsSection: () => <div>Targets section</div>,
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

describe('PluginDetailsDrawer description', () => {
  beforeEach(() => {
    getPluginDetails.mockReset()
  })

  it('shows the description, category and a documentation link', async () => {
    getPluginDetails.mockResolvedValue(details())
    render(<PluginDetailsDrawer pluginId={1} onClose={() => {}} onChanged={() => {}} />)

    expect(await screen.findByText('Check SSH server connection.')).toBeInTheDocument()
    expect(screen.getByText('Network Services')).toBeInTheDocument()

    const link = screen.getByRole('link', { name: 'Documentation' })
    expect(link).toHaveAttribute('href', 'https://www.nagios-plugins.org/doc/man/check_ssh.html')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('falls back to a message and no link for a plugin without a description', async () => {
    getPluginDetails.mockResolvedValue(
      details({ name: 'check_company', description: null, category: null, documentation_url: null }),
    )
    render(<PluginDetailsDrawer pluginId={1} onClose={() => {}} onChanged={() => {}} />)

    expect(await screen.findByText('No description available.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Documentation' })).not.toBeInTheDocument()
  })
})
