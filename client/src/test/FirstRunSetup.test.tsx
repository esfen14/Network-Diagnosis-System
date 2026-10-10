import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { FirstRunSetup } from '../components/layout/FirstRunSetup'

const reload = vi.fn()
vi.mock('../contexts/CurrentUserContext', () => ({
  useCurrentUser: () => ({ reload }),
}))

const apiPost = vi.fn()
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return { ...actual, apiPost: (path: string, data?: unknown) => apiPost(path, data) }
})

async function fillAndSubmit() {
  const user = userEvent.setup()
  render(<MemoryRouter><FirstRunSetup /></MemoryRouter>)
  await user.type(screen.getByLabelText('Current password'), 'OldPass1!abcd')
  await user.type(screen.getByLabelText('New email'), 'ops@company.com')
  await user.type(screen.getByLabelText('New password'), 'BrandNewPass1!xyz')
  await user.type(screen.getByLabelText('Confirm new password'), 'BrandNewPass1!xyz')
  await user.click(screen.getByRole('button', { name: 'Complete setup' }))
}

describe('FirstRunSetup', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('cannot be submitted until every field is filled and passwords match', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><FirstRunSetup /></MemoryRouter>)
    const submit = screen.getByRole('button', { name: 'Complete setup' })
    expect(submit).toBeDisabled()
    await user.type(screen.getByLabelText('New password'), 'a')
    await user.type(screen.getByLabelText('Confirm new password'), 'b')
    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument()
    expect(submit).toBeDisabled()
  })

  it('posts the four fields and reloads the user on success', async () => {
    apiPost.mockResolvedValue({ config_ok: true })
    await fillAndSubmit()
    await waitFor(() => expect(reload).toHaveBeenCalled())
    expect(apiPost).toHaveBeenCalledWith('/api/user/complete-setup', {
      current_password: 'OldPass1!abcd',
      new_email: 'ops@company.com',
      new_password: 'BrandNewPass1!xyz',
      confirm_password: 'BrandNewPass1!xyz',
    })
  })

  it('shows the server error and stays on the window', async () => {
    apiPost.mockRejectedValue(new Error('Email already exists.'))
    await fillAndSubmit()
    expect(await screen.findByRole('alert')).toHaveTextContent('Email already exists.')
    expect(reload).not.toHaveBeenCalled()
  })

  it('warns when Nagios was not updated and continues only on request', async () => {
    apiPost.mockResolvedValue({ config_ok: false, config_message: 'Config failed to validate' })
    await fillAndSubmit()
    expect(await screen.findByRole('alert')).toHaveTextContent('Config failed to validate')
    expect(reload).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Continue' }))
    expect(reload).toHaveBeenCalled()
  })
})
