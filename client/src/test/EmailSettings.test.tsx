import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { EmailSettings } from '../components/settings/EmailSettings'
import { ApiError } from '../lib/api'

const getSmtpSettings = vi.fn()
const saveSmtpSettings = vi.fn()
const sendTestEmail = vi.fn()

vi.mock('../lib/smtpSettingsApi', () => ({
  getSmtpSettings: () => getSmtpSettings(),
  saveSmtpSettings: (...args: unknown[]) => saveSmtpSettings(...args),
  sendTestEmail: () => sendTestEmail(),
}))

const preset = { provider: 'gmail', host: 'smtp.gmail.com', port: 587, tls: 'starttls' }

function loaded(overrides: Record<string, unknown> = {}) {
  return {
    settings: {
      ...preset, username: '', sender: '', passwordSet: false, configured: false, version: 0, updatedAt: null,
      ...overrides,
    },
    presets: { gmail: preset },
  }
}

const RAW_535 =
  '535 5.7.8 Username and Password not accepted. For more information, go to https://support.google.com/mail/?p=BadCredentials'

describe('EmailSettings', () => {
  beforeEach(() => {
    getSmtpSettings.mockReset().mockResolvedValue(loaded())
    saveSmtpSettings.mockReset()
    sendTestEmail.mockReset()
  })

  it('fills in the Gmail preset', async () => {
    render(<EmailSettings />)

    expect(await screen.findByLabelText('Host')).toHaveValue('smtp.gmail.com')
    expect(screen.getByLabelText('Port')).toHaveValue('587')
    expect(screen.getByLabelText('Security')).toHaveValue('STARTTLS')
  })

  it('explains app passwords and links to Google in a new tab', async () => {
    render(<EmailSettings />)

    expect(await screen.findByText(/Gmail does not accept your normal password here/)).toBeInTheDocument()
    expect(screen.getByText(/2-Step Verification turned on/)).toBeInTheDocument()
    expect(screen.getByText(/about 500 messages a day/)).toBeInTheDocument()
    const link = screen.getByRole('link', { name: /Create an app password/ })
    expect(link).toHaveAttribute('href', 'https://myaccount.google.com/apppasswords')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
  })

  it('labels the field "App password" with the xxxx placeholder', async () => {
    render(<EmailSettings />)

    expect(await screen.findByLabelText('App password')).toHaveAttribute('placeholder', 'xxxx xxxx xxxx xxxx')
  })

  it('the sender follows the username and warns when changed', async () => {
    render(<EmailSettings />)

    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'ops@gmail.com' } })
    expect(screen.getByLabelText('Sender')).toHaveValue('ops@gmail.com')
    expect(screen.queryByText(/Gmail rewrites the From address/)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Sender'), { target: { value: 'alerts@gmail.com' } })
    expect(screen.getByText(/Gmail rewrites the From address/)).toBeInTheDocument()
  })

  it('saves a password pasted with spaces exactly as typed', async () => {
    saveSmtpSettings.mockResolvedValue(loaded({ username: 'ops@gmail.com', sender: 'ops@gmail.com', passwordSet: true, configured: true, version: 1 }).settings)
    render(<EmailSettings />)

    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'ops@gmail.com' } })
    fireEvent.change(screen.getByLabelText('App password'), { target: { value: 'abcd efgh ijkl mnop' } })
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/ }))

    await waitFor(() => expect(saveSmtpSettings).toHaveBeenCalledTimes(1))
    expect(saveSmtpSettings).toHaveBeenCalledWith(
      { username: 'ops@gmail.com', sender: 'ops@gmail.com', password: 'abcd efgh ijkl mnop' },
      0,
    )
  })

  it('never shows the saved password and omits it when left blank', async () => {
    getSmtpSettings.mockResolvedValue(loaded({ username: 'ops@gmail.com', sender: 'ops@gmail.com', passwordSet: true, configured: true, version: 3 }))
    saveSmtpSettings.mockResolvedValue(loaded({ username: 'ops@gmail.com', sender: 'new@gmail.com', passwordSet: true, configured: true, version: 4 }).settings)
    render(<EmailSettings />)

    const password = await screen.findByLabelText('App password')
    expect(password).toHaveValue('')
    expect(password).toHaveAttribute('type', 'password')
    expect(screen.getByText(/An app password is saved/)).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Sender'), { target: { value: 'new@gmail.com' } })
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/ }))

    await waitFor(() => expect(saveSmtpSettings).toHaveBeenCalled())
    expect(saveSmtpSettings).toHaveBeenCalledWith({ username: 'ops@gmail.com', sender: 'new@gmail.com' }, 3)
  })

  it('shows the helper\'s error text when a save is refused', async () => {
    saveSmtpSettings.mockRejectedValue(new ApiError('username must be printable ASCII', 400))
    render(<EmailSettings />)

    fireEvent.change(await screen.findByLabelText('Username'), { target: { value: 'ops@gmail.com' } })
    fireEvent.change(screen.getByLabelText('App password'), { target: { value: 'abcd' } })
    fireEvent.click(screen.getByRole('button', { name: /Save Changes/ }))

    expect(await screen.findByText('username must be printable ASCII')).toBeInTheDocument()
  })

  describe('test email', () => {
    beforeEach(() => {
      getSmtpSettings.mockResolvedValue(loaded({ username: 'ops@gmail.com', sender: 'ops@gmail.com', passwordSet: true, configured: true, version: 1 }))
    })

    it('shows the friendly message for Gmail\'s 535 and the raw text under Details', async () => {
      sendTestEmail.mockResolvedValue({
        ok: false,
        code: 'auth_failed',
        message: 'Gmail rejected the login. Make sure you entered an app password, not your normal password, and that 2-Step Verification is on.',
        details: RAW_535,
      })
      render(<EmailSettings />)

      fireEvent.click(await screen.findByRole('button', { name: /Send test email/ }))

      expect(await screen.findByText(/Gmail rejected the login/)).toBeInTheDocument()
      expect(screen.getByText('Details')).toBeInTheDocument()
      expect(screen.getByText(RAW_535)).toBeInTheDocument()
    })

    it('shows other failures with their own message', async () => {
      sendTestEmail.mockResolvedValue({
        ok: false,
        code: 'connect_failed',
        message: 'Could not connect to smtp.gmail.com on port 587. The appliance needs outbound access to smtp.gmail.com on port 587; a firewall may be blocking it.',
        details: '[Errno 111] Connection refused',
      })
      render(<EmailSettings />)

      fireEvent.click(await screen.findByRole('button', { name: /Send test email/ }))

      expect(await screen.findByText(/Could not connect to smtp.gmail.com on port 587/)).toBeInTheDocument()
      expect(screen.queryByText(/Gmail rejected the login/)).not.toBeInTheDocument()
    })

    it('asks whether it arrived after a successful send', async () => {
      sendTestEmail.mockResolvedValue({ ok: true, recipient: 'admin@example.com' })
      render(<EmailSettings />)

      fireEvent.click(await screen.findByRole('button', { name: /Send test email/ }))

      expect(await screen.findByText(/Test email sent to admin@example.com/)).toBeInTheDocument()
      expect(screen.getByText(/Did it arrive\?/)).toBeInTheDocument()
    })

    it('is disabled until the settings are saved', async () => {
      getSmtpSettings.mockResolvedValue(loaded())
      render(<EmailSettings />)

      expect(await screen.findByRole('button', { name: /Send test email/ })).toBeDisabled()
    })
  })
})
