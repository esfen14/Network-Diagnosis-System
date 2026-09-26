import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ManageAccountsPage } from '../pages/ManageAccountsPage'

let strongPasswordPolicy = true
vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ settings: { strongPasswordPolicy } }),
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

function routeApi(path: string) {
  if (path.startsWith('/api/user/accounts')) {
    return accountsResponse instanceof Error ? Promise.reject(accountsResponse) : Promise.resolve(accountsResponse)
  }
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
        })
      })
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
})
