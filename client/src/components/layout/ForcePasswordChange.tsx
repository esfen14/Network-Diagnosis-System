import { useState } from 'react'
import { KeyRound } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useCurrentUser } from '../../contexts/CurrentUserContext'
import { apiPost, errorMessage } from '../../lib/api'
import { LoginBackdrop } from './LoginBackdrop'

const INPUT_CLASS =
  'w-full rounded-full border border-[var(--border)] bg-[var(--input-bg)] px-4 py-2.5 text-sm text-[var(--text)] outline-none focus:border-[#ffb100]'

export function ForcePasswordChange() {
  const { reload } = useCurrentUser()
  const navigate = useNavigate()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mismatch = confirmPassword !== '' && newPassword !== confirmPassword
  const canSave = currentPassword !== '' && newPassword !== '' && newPassword === confirmPassword && !isSaving

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!canSave) return
    setIsSaving(true)
    setError(null)
    try {
      await apiPost('/api/user/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      })
      reload()
    } catch (err) {
      setError(errorMessage(err, 'Unable to change the password.'))
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

  return (
    <LoginBackdrop>
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md rounded-3xl border border-[var(--border)] bg-[var(--card)] p-8 shadow-xl"
      >
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#F4A90B]">
          <KeyRound className="h-7 w-7 text-white" />
        </div>
        <h1 className="text-center text-xl font-semibold text-[var(--text)]">Change your password</h1>
        <p className="mt-2 text-center text-sm text-[var(--text-muted)]">
          Your password was set or reset by an administrator. Choose a new one to continue.
        </p>

        <div className="mt-6 space-y-4">
          <div>
            <label htmlFor="current-password" className="mb-1.5 block text-sm text-[var(--text)]">
              Current (temporary) password
            </label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label htmlFor="new-password" className="mb-1.5 block text-sm text-[var(--text)]">
              New password
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label htmlFor="confirm-password" className="mb-1.5 block text-sm text-[var(--text)]">
              Confirm new password
            </label>
            <input
              id="confirm-password"
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
            {isSaving ? 'Saving…' : 'Change password'}
          </button>
        </div>
      </form>
    </LoginBackdrop>
  )
}
