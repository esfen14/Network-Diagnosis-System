import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Header } from '../components/layout/Header'
import { MaintenanceBanner } from '../components/layout/MaintenanceBanner'

const savedSettings = { notifications: true, maintenanceMode: false }

vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ savedSettings }),
}))

let permissions = ['system.notifications']
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({
    user: null,
    isLoading: false,
    hasPermission: (permission: string) => permissions.includes(permission),
  }),
}))

const apiGet = vi.fn()
vi.mock('../lib/api', () => ({
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(() => Promise.resolve({})),
}))

function renderHeader() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Header />
    </MemoryRouter>,
  )
}

describe('Notifications setting', () => {
  beforeEach(() => {
    permissions = ['system.notifications']
    apiGet.mockReset()
    apiGet.mockResolvedValue({ unread_count: 3 })
  })

  it('shows the bell and polls unread count when enabled', async () => {
    savedSettings.notifications = true
    renderHeader()

    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument()
    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/api/system/notifications/unread-count')
  })

  it('hides the bell when the role lacks the notifications permission', () => {
    savedSettings.notifications = true
    permissions = []
    renderHeader()

    expect(screen.queryByRole('button', { name: 'Notifications' })).not.toBeInTheDocument()
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('hides the bell and stops polling when disabled', () => {
    savedSettings.notifications = false
    renderHeader()

    expect(screen.queryByRole('button', { name: 'Notifications' })).not.toBeInTheDocument()
    expect(apiGet).not.toHaveBeenCalled()
  })
})

describe('MaintenanceBanner', () => {
  it('is hidden when maintenance mode is off', () => {
    savedSettings.maintenanceMode = false
    render(<MaintenanceBanner />)

    expect(screen.queryByText(/maintenance mode is on/i)).not.toBeInTheDocument()
  })

  it('is shown when maintenance mode is on', () => {
    savedSettings.maintenanceMode = true
    render(<MaintenanceBanner />)

    expect(screen.getByText(/maintenance mode is on/i)).toBeInTheDocument()
  })
})
