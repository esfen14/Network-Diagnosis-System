import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { LoginPage } from '../pages/LoginPage'

// Mock useNavigate
const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

function renderLoginPage() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    mockNavigate.mockReset()
    vi.spyOn(window, 'alert').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders email and password inputs', () => {
    renderLoginPage()
    expect(screen.getByPlaceholderText('Enter your email')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('•••••••••••••••')).toBeInTheDocument()
  })

  it('renders the Log In button', () => {
    renderLoginPage()
    expect(screen.getByRole('button', { name: /log in/i })).toBeInTheDocument()
  })

  it('shows password when eye icon is clicked (Show password)', async () => {
    const user = userEvent.setup()
    renderLoginPage()

    const passwordInput = screen.getByPlaceholderText('•••••••••••••••')
    expect(passwordInput).toHaveAttribute('type', 'password')

    const showBtn = screen.getByRole('button', { name: 'Show password' })
    await user.click(showBtn)

    expect(passwordInput).toHaveAttribute('type', 'text')
    expect(screen.getByRole('button', { name: 'Hide password' })).toBeInTheDocument()
  })

  it('hides password when eye icon is clicked again (Hide password)', async () => {
    const user = userEvent.setup()
    renderLoginPage()

    const showBtn = screen.getByRole('button', { name: 'Show password' })
    await user.click(showBtn)

    const hideBtn = screen.getByRole('button', { name: 'Hide password' })
    await user.click(hideBtn)

    const passwordInput = screen.getByPlaceholderText('•••••••••••••••')
    expect(passwordInput).toHaveAttribute('type', 'password')
  })

  it('navigates to /dashboard on successful login', async () => {
    const user = userEvent.setup()

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({ message: 'Login successful' }),
    } as Response)

    renderLoginPage()

    await user.type(screen.getByPlaceholderText('Enter your email'), 'admin@test.com')
    await user.type(screen.getByPlaceholderText('•••••••••••••••'), 'password123')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard')
    })
  })

  it('shows alert on failed login (401)', async () => {
    const user = userEvent.setup()
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})

    vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: false,
      json: async () => ({ message: 'Invalid username or password.' }),
    } as Response)

    renderLoginPage()

    await user.type(screen.getByPlaceholderText('Enter your email'), 'bad@test.com')
    await user.type(screen.getByPlaceholderText('•••••••••••••••'), 'wrongpass')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Invalid username or password.')
    })
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('shows "Unable to connect to server" alert on network error', async () => {
    const user = userEvent.setup()
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})

    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('Network Error'))

    renderLoginPage()

    await user.type(screen.getByPlaceholderText('Enter your email'), 'admin@test.com')
    await user.type(screen.getByPlaceholderText('•••••••••••••••'), 'password123')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Unable to connect to server')
    })
  })

  it('shows LOGGING IN... text while loading', async () => {
    const user = userEvent.setup()

    // Never resolve so we can check the loading state
    vi.spyOn(global, 'fetch').mockImplementation(
      () => new Promise(() => {}),
    )

    renderLoginPage()

    await user.type(screen.getByPlaceholderText('Enter your email'), 'admin@test.com')
    await user.type(screen.getByPlaceholderText('•••••••••••••••'), 'password123')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /logging in/i })).toBeInTheDocument()
    })
  })

  it('remember me checkbox toggles', async () => {
    const user = userEvent.setup()
    renderLoginPage()

    const checkbox = screen.getByRole('checkbox', { name: /remember me/i })
    expect(checkbox).not.toBeChecked()

    await user.click(checkbox)
    expect(checkbox).toBeChecked()

    await user.click(checkbox)
    expect(checkbox).not.toBeChecked()
  })

  it('submits form with typed email and password', async () => {
    const user = userEvent.setup()
    const fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    } as Response)

    renderLoginPage()

    await user.type(screen.getByPlaceholderText('Enter your email'), 'user@example.com')
    await user.type(screen.getByPlaceholderText('•••••••••••••••'), 'secret')
    await user.click(screen.getByRole('button', { name: /log in/i }))

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        'http://127.0.0.1:5000/user/login',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ email: 'user@example.com', password: 'secret' }),
        }),
      )
    })
  })
})
