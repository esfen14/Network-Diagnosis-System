import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ManageAccountsPage } from '../pages/ManageAccountsPage'

let strongPasswordPolicy = true
vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ settings: { strongPasswordPolicy } }),
}))

let canEditAccounts = false
let canEditAlerts = false
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({
    user: null,
    isLoading: false,
    hasPermission: (name: string) =>
      (canEditAccounts && name === 'account.edit') || (canEditAlerts && name === 'account.alerts'),
  }),
}))

const apiGet = vi.fn()
const apiPost = vi.fn()
const apiPut = vi.fn()

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    apiGet: (path: string) => apiGet(path),
    apiPost: (path: string, data?: unknown) => apiPost(path, data),
    apiPut: (path: string, data?: unknown) => apiPut(path, data),
  }
})

// ─── API fixtures (server/app/api/user/management.py shapes) ────────────────
// Backend statuses are Active / Inactive / Suspended (UserStatus enum).

function account(id: number, first: string, last: string, status: string, role = 'Admin') {
  return {
    id,
    first_name: first,
    last_name: last,
    email: `${first.toLowerCase()}@example.com`,
    role,
    status,
    receive_email_alerts: true,
    created_at: '2026-09-01T08:00:00+00:00',
    updated_at: '2026-09-01T08:00:00+00:00',
  }
}

const ACCOUNTS = [
  account(1, 'Marie', 'Santos', 'Active'),
  account(2, 'Chloe', 'Baltazar', 'Active', 'Viewer'),
  account(3, 'Lucas', 'Mitchell', 'Active', 'Viewer'),
  account(4, 'John', 'Cruz', 'Inactive', 'Viewer'),
  account(5, 'Marco', 'Gomez', 'Suspended', 'Viewer'),
]

const ROLES = [{ id: 1, name: 'Admin' }, { id: 2, name: 'Viewer' }]

let accountsResponse: unknown
let passwordRequests: unknown[] = []

function routeApi(path: string) {
  if (path.startsWith('/api/user/accounts')) {
    return accountsResponse instanceof Error ? Promise.reject(accountsResponse) : Promise.resolve(accountsResponse)
  }
  if (path === '/api/user/password-requests') return Promise.resolve({ items: passwordRequests })
  if (path.startsWith('/api/user/roles/options')) return Promise.resolve({ items: ROLES })
  return Promise.resolve(null)
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ManageAccountsPage />
    </MemoryRouter>,
  )
}

async function renderLoaded() {
  renderPage()
  await waitFor(() => expect(screen.queryByText('Loading users…')).not.toBeInTheDocument())
}

function tableNames() {
  return screen
    .getAllByRole('row')
    .slice(1)
    .map((row) => within(row).queryAllByRole('cell')[0]?.textContent)
    .filter(Boolean)
}

describe('ManageAccountsPage', () => {
  beforeEach(() => {
    strongPasswordPolicy = true
    canEditAccounts = false
    canEditAlerts = false
    passwordRequests = []
    accountsResponse = { items: ACCOUNTS }
    apiGet.mockReset()
    apiPost.mockReset()
    apiPut.mockReset()
    apiGet.mockImplementation(routeApi)
    apiPost.mockResolvedValue({})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("shows the 'User Management' heading", async () => {
    await renderLoaded()
    expect(screen.getByText('User Management')).toBeInTheDocument()
  })

  it('loads accounts and role options', async () => {
    await renderLoaded()
    const paths = apiGet.mock.calls.map(([path]) => path)
    expect(paths).toContain('/api/user/accounts?per_page=100')
    expect(paths).toContain('/api/user/roles/options')
  })

  it('shows a filter tab for each backend status', async () => {
    await renderLoaded()
    for (const name of ['All', 'Active', 'Inactive', 'Suspended']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
    expect(screen.queryByRole('button', { name: 'Locked' })).not.toBeInTheDocument()
  })

  it('shows the Export and + Add User buttons', async () => {
    await renderLoaded()
    expect(screen.getByRole('button', { name: 'Export' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '+ Add User' })).toBeInTheDocument()
  })

  it('lists every account by default', async () => {
    await renderLoaded()
    expect(tableNames()).toHaveLength(5)
    expect(screen.getByText('Marie Santos')).toBeInTheDocument()
    expect(screen.getByText('marie@example.com')).toBeInTheDocument()
  })

  it('filters by Active', async () => {
    const user = userEvent.setup()
    await renderLoaded()
    await user.click(screen.getByRole('button', { name: 'Active' }))
    expect(tableNames()).toEqual(expect.arrayContaining(['Marie Santos', 'Chloe Baltazar', 'Lucas Mitchell']))
    expect(tableNames()).toHaveLength(3)
  })

  it('filters by Inactive', async () => {
    const user = userEvent.setup()
    await renderLoaded()
    await user.click(screen.getByRole('button', { name: 'Inactive' }))
    expect(tableNames()).toEqual(['John Cruz'])
  })

  it('filters by Suspended', async () => {
    const user = userEvent.setup()
    await renderLoaded()
    await user.click(screen.getByRole('button', { name: 'Suspended' }))
    expect(tableNames()).toEqual(['Marco Gomez'])
  })

  it("restores every account when 'All' is clicked after filtering", async () => {
    const user = userEvent.setup()
    await renderLoaded()
    await user.click(screen.getByRole('button', { name: 'Suspended' }))
    await user.click(screen.getByRole('button', { name: 'All' }))
    expect(tableNames()).toHaveLength(5)
  })

  it('disables Export when there are no accounts', async () => {
    accountsResponse = { items: [] }
    await renderLoaded()
    expect(screen.getByRole('button', { name: 'Export' })).toBeDisabled()
  })

  it('shows an error banner when loading fails', async () => {
    accountsResponse = new Error('Unable to reach server')
    renderPage()
    expect(await screen.findByText('Unable to reach server')).toBeInTheDocument()
  })

  describe('Password reset requests', () => {
    const REQUEST = {
      id: 7,
      user_id: 3,
      name: 'Marie Santos',
      email: 'marie@example.com',
      requested_at: '2026-10-08T08:00:00+00:00',
    }

    it('is hidden from users who cannot edit accounts', async () => {
      passwordRequests = [REQUEST]
      await renderLoaded()
      expect(screen.queryByText(/Password reset requests/)).not.toBeInTheDocument()
    })

    it('lets an admin set a temporary password for a pending request', async () => {
      canEditAccounts = true
      passwordRequests = [REQUEST]
      const user = userEvent.setup()
      await renderLoaded()

      expect(await screen.findByText('Password reset requests (1)')).toBeInTheDocument()
      await user.click(screen.getByRole('button', { name: 'Reset password' }))

      const dialog = screen.getByRole('dialog', { name: 'Reset password' })
      await user.type(within(dialog).getByLabelText('TEMPORARY PASSWORD'), 'StrongPass123!')
      await user.type(within(dialog).getByLabelText('CONFIRM PASSWORD'), 'StrongPass123!')
      await user.click(within(dialog).getByRole('button', { name: 'Reset password' }))

      await waitFor(() =>
        expect(apiPost).toHaveBeenCalledWith('/api/user/password-requests/7/resolve', {
          password: 'StrongPass123!',
          confirm_password: 'StrongPass123!',
        }),
      )
    })
  })

  describe('Add User', () => {
    async function openAndFill(password: string, confirm = password) {
      const user = userEvent.setup()
      await renderLoaded()
      await user.click(screen.getByRole('button', { name: '+ Add User' }))
      await user.type(screen.getByPlaceholderText('e.g. JUAN'), 'Ana')
      await user.type(screen.getByPlaceholderText('e.g. CRUZ'), 'Reyes')
      await user.type(screen.getByPlaceholderText('e.g. juan.cruz@email.com'), 'ana@example.com')
      const [passwordInput, confirmInput] = document.querySelectorAll<HTMLInputElement>('input[type="password"]')
      await user.type(passwordInput, password)
      await user.type(confirmInput, confirm)
      return user
    }

    it('creates an account with a strong password', async () => {
      const user = await openAndFill('StrongPass123!')

      await user.click(screen.getByRole('button', { name: 'SAVE CHANGES' }))

      await waitFor(() => {
        expect(apiPost).toHaveBeenCalledWith('/api/user/accounts', {
          first_name: 'Ana',
          last_name: 'Reyes',
          email: 'ana@example.com',
          password: 'StrongPass123!',
          confirm_password: 'StrongPass123!',
          status: 'active',
          role_id: 1,
          require_password_change: true,
        })
      })
    })

    it('sends require_password_change false when the checkbox is unticked', async () => {
      const user = await openAndFill('StrongPass123!')
      const box = screen.getByLabelText('Require password change at first sign-in')
      expect(box).toBeChecked()
      await user.click(box)

      await user.click(screen.getByRole('button', { name: 'SAVE CHANGES' }))

      await waitFor(() =>
        expect(apiPost).toHaveBeenCalledWith(
          '/api/user/accounts',
          expect.objectContaining({ require_password_change: false }),
        ),
      )
    })

    it('blocks a weak password under the strong policy', async () => {
      await openAndFill('weakpass')
      expect(screen.getByText(/12\+ characters/)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'SAVE CHANGES' })).toBeDisabled()
    })

    it('accepts an 8-character password under the relaxed policy', async () => {
      strongPasswordPolicy = false
      await openAndFill('weakpass')
      expect(screen.getByText('Passwords need at least 8 characters.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'SAVE CHANGES' })).toBeEnabled()
    })

    it('warns when the passwords do not match', async () => {
      await openAndFill('StrongPass123!', 'StrongPass123?')
      expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'SAVE CHANGES' })).toBeDisabled()
    })
  })
  describe('Email alerts', () => {
    it('shows each account\'s setting in the table', async () => {
      accountsResponse = {
        items: [account(1, 'Marie', 'Santos', 'Active'), { ...account(2, 'Chloe', 'Baltazar', 'Active'), receive_email_alerts: false }],
      }
      await renderLoaded()
      const rows = screen.getAllByRole('row').slice(1)
      expect(within(rows[0]).getByText('On')).toBeInTheDocument()
      expect(within(rows[1]).getByText('Off')).toBeInTheDocument()
    })

    it('hides the toggle without the account.alerts permission', async () => {
      const user = userEvent.setup()
      await renderLoaded()
      await user.click(screen.getByRole('button', { name: '+ Add User' }))
      expect(screen.queryByLabelText('Send this user email alerts')).not.toBeInTheDocument()
    })

    it('does not send the field when the user cannot change it', async () => {
      const user = userEvent.setup()
      await renderLoaded()
      await user.click(screen.getAllByTitle('Edit')[0])
      await user.click(screen.getByRole('button', { name: 'Save Changes' }))

      await waitFor(() => expect(apiPut).toHaveBeenCalled())
      expect(apiPut.mock.calls[0][1]).not.toHaveProperty('receive_email_alerts')
    })

    it('sends the setting when creating an account', async () => {
      canEditAlerts = true
      const user = userEvent.setup()
      await renderLoaded()
      await user.click(screen.getByRole('button', { name: '+ Add User' }))
      await user.type(screen.getByPlaceholderText('e.g. JUAN'), 'Ana')
      await user.type(screen.getByPlaceholderText('e.g. CRUZ'), 'Reyes')
      await user.type(screen.getByPlaceholderText('e.g. juan.cruz@email.com'), 'ana@example.com')
      const [passwordInput, confirmInput] = document.querySelectorAll<HTMLInputElement>('input[type="password"]')
      await user.type(passwordInput, 'StrongPass123!')
      await user.type(confirmInput, 'StrongPass123!')

      const box = screen.getByLabelText('Send this user email alerts')
      expect(box).toBeChecked()
      await user.click(box)
      await user.click(screen.getByRole('button', { name: 'SAVE CHANGES' }))

      await waitFor(() =>
        expect(apiPost).toHaveBeenCalledWith(
          '/api/user/accounts',
          expect.objectContaining({ receive_email_alerts: false }),
        ),
      )
    })

    it('sends the setting when editing an account', async () => {
      canEditAlerts = true
      apiPut.mockResolvedValue({})
      const user = userEvent.setup()
      await renderLoaded()
      await user.click(screen.getAllByTitle('Edit')[0])
      await user.click(screen.getByLabelText('Send this user email alerts'))
      await user.click(screen.getByRole('button', { name: 'Save Changes' }))

      await waitFor(() =>
        expect(apiPut).toHaveBeenCalledWith(
          '/api/user/accounts/1',
          expect.objectContaining({ receive_email_alerts: false }),
        ),
      )
    })

    it('tells the user when Nagios was not updated', async () => {
      canEditAlerts = true
      apiPut.mockResolvedValue({ config_ok: false, config_message: 'nagios -v failed' })
      const user = userEvent.setup()
      await renderLoaded()
      await user.click(screen.getAllByTitle('Edit')[0])
      await user.click(screen.getByLabelText('Send this user email alerts'))
      await user.click(screen.getByRole('button', { name: 'Save Changes' }))

      expect(
        await screen.findByText('The account was saved but Nagios was not updated: nagios -v failed'),
      ).toBeInTheDocument()
    })
  })
})
