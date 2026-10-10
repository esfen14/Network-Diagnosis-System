import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useCurrentUser } from '../../contexts/CurrentUserContext'
import { apiPost, errorMessage } from '../../lib/api'

const INPUT_CLASS =
  'w-full rounded-full border border-[var(--border)] bg-[var(--input-bg)] px-4 py-2.5 text-sm text-[var(--text)] outline-none focus:border-[#ffb100]'

type SetupResult = { config_ok?: boolean; config_message?: string }

export function FirstRunSetup() {
  const { reload } = useCurrentUser()
  const navigate = useNavigate()
  const [currentPassword, setCurrentPassword] = useState('')
  const [email, setEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)

  const mismatch = confirmPassword !== '' && newPassword !== confirmPassword
  const canSave =
    currentPassword !== '' &&
    email.trim() !== '' &&
    newPassword !== '' &&
    newPassword === confirmPassword &&
    !isSaving

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!canSave) return
    setIsSaving(true)
    setError(null)
    try {
      const result = await apiPost<SetupResult>('/api/user/complete-setup', {
        current_password: currentPassword,
        new_email: email.trim(),
        new_password: newPassword,
        confirm_password: confirmPassword,
      })
      if (result?.config_ok === false) {
        setWarning(result.config_message || 'The Nagios contact could not be updated.')
      } else {
        reload()
      }
    } catch (err) {
      setError(errorMessage(err, 'Unable to complete setup.'))
    } finally {
      setIsSaving(false)
    }
  }

  const handleSignOut = async () => {
    try {
      await apiPost('/api/user/logout')
    } catch {
      // Sign out locally even if the server call fails.
    }
    localStorage.clear()
    sessionStorage.clear()
    navigate('/login', { replace: true })
  }

  if (warning) {
    return (
      <div className="admin-bg flex min-h-screen items-center justify-center p-4">
        <div className="w-full max-w-md rounded-3xl border border-[var(--border)] bg-[var(--card)] p-8 shadow-xl">
          <h1 className="text-center text-xl font-semibold text-[var(--text)]">Setup saved</h1>
          <p role="alert" className="mt-3 text-center text-sm text-amber-600 dark:text-amber-400">
            Your email and password were saved, but Nagios could not be updated with your new
            address, so alerts may still go to the old one. {warning}
          </p>
          <div className="mt-6 flex justify-center">
            <button
              type="button"
              onClick={reload}
              className="rounded-full bg-[#ffb100] px-6 py-2.5 text-sm font-semibold text-black"
            >
              Continue
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="admin-bg flex min-h-screen items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-3xl border border-[var(--border)] bg-[var(--card)] p-8 shadow-xl"
      >
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#F4A90B]">
          <ShieldCheck className="h-7 w-7 text-white" />
        </div>
        <h1 className="text-center text-xl font-semibold text-[var(--text)]">Finish setting up Pinpoint</h1>
        <p className="mt-2 text-center text-sm text-[var(--text-muted)]">
          The installer created this account with a placeholder email and a generated password.
          Enter a real email address (alert notifications are sent to it) and choose a new password.
        </p>

        <div className="mt-6 space-y-4">
          <div>
            <label htmlFor="setup-current-password" className="mb-1.5 block text-sm text-[var(--text)]">
              Current password
            </label>
            <input
              id="setup-current-password"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label htmlFor="setup-email" className="mb-1.5 block text-sm text-[var(--text)]">
              New email
            </label>
            <input
              id="setup-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label htmlFor="setup-new-password" className="mb-1.5 block text-sm text-[var(--text)]">
              New password
            </label>
            <input
              id="setup-new-password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label htmlFor="setup-confirm-password" className="mb-1.5 block text-sm text-[var(--text)]">
              Confirm new password
            </label>
            <input
              id="setup-confirm-password"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          {mismatch && <p className="text-xs text-red-500 dark:text-red-400">Passwords do not match.</p>}
          {error && (
            <p role="alert" className="text-sm text-red-500 dark:text-red-400">
              {error}
            </p>
          )}
        </div>

        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={handleSignOut}
            className="rounded-full border border-[#ffb100] px-6 py-2.5 text-sm font-medium text-[#ffb100] hover:bg-[#ffb100]/10"
          >
            Sign out
          </button>
          <button
            type="submit"
            disabled={!canSave}
            className="rounded-full bg-[#ffb100] px-6 py-2.5 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving ? 'Saving…' : 'Complete setup'}
          </button>
        </div>
      </form>
    </div>
  )
}
