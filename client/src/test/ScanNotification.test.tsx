import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Header } from '../components/layout/Header'

const savedSettings = { notifications: false, maintenanceMode: false }

vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ savedSettings }),
}))

let permissions = ['system.discover']
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({
    user: null,
    isLoading: false,
    hasPermission: (permission: string) => permissions.includes(permission),
  }),
}))

const apiGet = vi.fn()
const apiPost = vi.fn()
vi.mock('../lib/api', () => ({
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string) => apiPost(path),
  errorMessage: (err: unknown, fallback: string) => (err instanceof Error ? err.message : fallback),
}))

function scanStatus(overrides: Record<string, unknown> = {}) {
  return {
    id: 7,
    status: 'Running',
    progress: 42,
    message: 'Scanning TCP ports',
    start_at: '2026-09-30T10:00:00+00:00',
    completed_at: null,
    error: null,
    ...overrides,
  }
}

function renderHeader() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Header />
    </MemoryRouter>,
  )
}

async function openPanel() {
  fireEvent.click(screen.getByRole('button', { name: 'Notifications' }))
}

describe('Network scan in the notification panel', () => {
  beforeEach(() => {
    permissions = ['system.discover']
    savedSettings.notifications = false
    apiGet.mockReset()
    apiPost.mockReset()
  })

  it('shows progress and a Cancel button while a scan runs', async () => {
    apiGet.mockResolvedValue(scanStatus())
    renderHeader()
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/system/discover/status'))
    await openPanel()

    expect(await screen.findByText('Network scan in progress')).toBeInTheDocument()
    expect(screen.getByText('42%')).toBeInTheDocument()
    expect(screen.getByText('Scanning TCP ports')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Network scan progress' })).toHaveAttribute('aria-valuenow', '42')
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
  })

  it('cancels the scan through the stop route', async () => {
    apiGet.mockResolvedValue(scanStatus())
    apiPost.mockResolvedValue({})
    renderHeader()
    await openPanel()

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))

    expect(apiPost).toHaveBeenCalledWith('/api/system/network-discovery/stop')
    expect(await screen.findByText('Cancelling network scan…')).toBeInTheDocument()
  })

  it('shows the cancel error when stopping fails', async () => {
    apiGet.mockResolvedValue(scanStatus())
    apiPost.mockRejectedValue(new Error('There is no network discovery running.'))
    renderHeader()
    await openPanel()

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('There is no network discovery running.')
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled()
  })

  it('shows a completed scan without a Cancel button', async () => {
    apiGet.mockResolvedValue(
      scanStatus({ status: 'Success', progress: 100, message: 'New host.cfg successfully applied', completed_at: '2026-09-30T10:05:00+00:00' }),
    )
    renderHeader()
    await openPanel()

    expect(await screen.findByText('Network scan complete')).toBeInTheDocument()
    expect(screen.getByText('New host.cfg successfully applied')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument()
  })

  it('shows the error of a failed scan', async () => {
    apiGet.mockResolvedValue(scanStatus({ status: 'Failed', progress: 100, error: 'nagios -v reported 2 errors' }))
    renderHeader()
    await openPanel()

    expect(await screen.findByText('Network scan failed')).toBeInTheDocument()
    expect(screen.getByText('nagios -v reported 2 errors')).toBeInTheDocument()
  })

  it('does not poll scan status or show the bell without the discover permission', () => {
    permissions = []
    renderHeader()

    expect(screen.queryByRole('button', { name: 'Notifications' })).not.toBeInTheDocument()
    expect(apiGet).not.toHaveBeenCalled()
  })
})
