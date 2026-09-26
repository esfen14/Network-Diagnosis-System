import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { canAccessPage, firstAccessiblePage } from '../lib/pageAccess'
import { PageAccessGuard } from '../components/layout/PageAccessGuard'
import { Sidebar } from '../components/layout/Sidebar'
import { SettingsPage } from '../pages/SettingsPage'

let currentUser: { permissions: string[]; firstName: string; lastName: string; email: string; role: string } | null

vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({
    user: currentUser,
    isLoading: false,
    hasPermission: (permission: string) => currentUser?.permissions.includes(permission) ?? false,
  }),
}))

// Settings tabs render real forms; stub them to keep this about which tabs show.
vi.mock('../components/settings/GeneralSettings', () => ({ GeneralSettings: () => <div>General form</div> }))
vi.mock('../components/settings/SecuritySettings', () => ({ SecuritySettings: () => <div>Security form</div> }))
vi.mock('../components/settings/SystemSettings', () => ({ SystemSettings: () => <div>System form</div> }))
vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ refreshSettings: () => Promise.resolve() }),
}))

function signIn(permissions: string[]) {
  currentUser = { permissions, firstName: 'Test', lastName: 'User', email: 't@test.com', role: 'Staff' }
}

describe('pageAccess', () => {
  it('allows a page when the role has its permission', () => {
    expect(canAccessPage('/dashboard', ['system.dashboard'])).toBe(true)
    expect(canAccessPage('/dashboard', [])).toBe(false)
  })

  it('always allows Settings', () => {
    expect(canAccessPage('/settings', [])).toBe(true)
  })

  it('picks the first accessible page in sidebar order, falling back to Settings', () => {
    expect(firstAccessiblePage(['plugin.view', 'system.report'])).toBe('/plugins')
    expect(firstAccessiblePage([])).toBe('/settings')
  })
})

describe('Sidebar', () => {
  beforeEach(() => signIn([]))

  it('shows only permitted pages plus Settings', () => {
    signIn(['system.dashboard', 'plugin.view'])
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )

    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Plugins')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
    expect(screen.queryByText('Manage Roles')).not.toBeInTheDocument()
    expect(screen.queryByText('System Logs')).not.toBeInTheDocument()
  })
})

describe('PageAccessGuard', () => {
  function renderAt(path: string) {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          {['/dashboard', '/plugins', '/manage-roles', '/settings'].map((route) => (
            <Route
              key={route}
              path={route}
              element={<PageAccessGuard><div>Page {route}</div></PageAccessGuard>}
            />
          ))}
        </Routes>
      </MemoryRouter>,
    )
  }

  it('renders a permitted page', () => {
    signIn(['role.view'])
    renderAt('/manage-roles')

    expect(screen.getByText('Page /manage-roles')).toBeInTheDocument()
  })

  it('redirects from a forbidden page to the first permitted one', () => {
    signIn(['plugin.view'])
    renderAt('/manage-roles')

    expect(screen.getByText('Page /plugins')).toBeInTheDocument()
  })

  it('redirects to Settings when nothing else is permitted', () => {
    signIn([])
    renderAt('/dashboard')

    expect(screen.getByText('Page /settings')).toBeInTheDocument()
  })
})

describe('SettingsPage tabs', () => {
  function renderSettings() {
    return render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    )
  }

  it('shows only General without settings permissions', () => {
    signIn([])
    renderSettings()

    expect(screen.getByRole('button', { name: /general settings/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /security/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^system$/i })).not.toBeInTheDocument()
  })

  it('shows each tab the role grants', () => {
    signIn(['settings.security'])
    renderSettings()

    expect(screen.getByRole('button', { name: /security/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^system$/i })).not.toBeInTheDocument()
  })

  it('shows all tabs with both permissions', () => {
    signIn(['settings.security', 'settings.system'])
    renderSettings()

    expect(screen.getByRole('button', { name: /security/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^system$/i })).toBeInTheDocument()
  })
})
