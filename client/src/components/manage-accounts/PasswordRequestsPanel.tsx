import { KeyRound, X } from 'lucide-react'
import { useState } from 'react'
import { useDisplayTime } from '../../hooks/useDisplayTime'
import type { PasswordRequest } from '../../hooks/usePasswordRequests'
import { apiPost, errorMessage } from '../../lib/api'

const INPUT_CLASS =
  'w-full rounded-full border border-[var(--border)] bg-[var(--input-bg)] px-4 py-2.5 text-sm text-[var(--text)] outline-none'

export function PasswordRequestsPanel({
  requests,
  isPasswordValid,
  passwordHint,
  onChanged,
}: {
  requests: PasswordRequest[]
  isPasswordValid: (password: string) => boolean
  passwordHint: string
  onChanged: () => void
}) {
  const { formatDateTime } = useDisplayTime()
  const [resetting, setResetting] = useState<PasswordRequest | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (requests.length === 0) return null

  async function dismiss(request: PasswordRequest) {
    setError(null)
    try {
      await apiPost(`/api/user/password-requests/${request.id}/dismiss`)
      onChanged()
    } catch (err) {
      setError(errorMessage(err, 'Unable to dismiss the request.'))
    }
  }

  return (
    <section
      aria-label="Password reset requests"
      className="rounded-2xl border border-[#ffb100]/40 bg-[#ffb100]/5 p-5"
    >
      <h2 className="flex items-center gap-2 text-sm font-semibold text-[var(--text)]">
        <KeyRound className="h-4 w-4 text-[#ffb100]" />
        Password reset requests ({requests.length})
      </h2>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        These users asked for a password reset from the login page. Set a temporary password and
        give it to them; they must change it at their next login.
      </p>

      <ul className="mt-3 divide-y divide-[var(--border)]">
        {requests.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
            <div className="text-sm">
              <p className="font-medium text-[var(--text)]">{r.name}</p>
              <p className="text-xs text-[var(--text-muted)]">
                {r.email} · requested {formatDateTime(r.requestedAt.getTime())}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => dismiss(r)}
                className="rounded-full border border-[var(--border)] px-4 py-1.5 text-xs font-medium text-[var(--text)] hover:bg-[var(--hover)]"
              >
                Dismiss
              </button>
              <button
                type="button"
                onClick={() => setResetting(r)}
                className="rounded-full bg-[#ffb100] px-4 py-1.5 text-xs font-semibold text-black hover:brightness-105"
              >
                Reset password
              </button>
            </div>
          </li>
        ))}
      </ul>

      {error && <p role="alert" className="mt-2 text-xs text-red-500">{error}</p>}

      {resetting && (
        <ResetPasswordModal
          request={resetting}
          isPasswordValid={isPasswordValid}
          passwordHint={passwordHint}
          onCancel={() => setResetting(null)}
          onDone={() => {
            setResetting(null)
            onChanged()
          }}
        />
      )}
    </section>
  )
}

function ResetPasswordModal({
  request,
  isPasswordValid,
  passwordHint,
  onCancel,
  onDone,
}: {
  request: PasswordRequest
  isPasswordValid: (password: string) => boolean
  passwordHint: string
  onCancel: () => void
  onDone: () => void
}) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const valid = password === confirm && isPasswordValid(password)

  async function save() {
    if (!valid) return
    setIsSaving(true)
    setError(null)
    try {
      await apiPost(`/api/user/password-requests/${request.id}/resolve`, {
        password,
        confirm_password: confirm,
      })
      onDone()
    } catch (err) {
      setError(errorMessage(err, 'Unable to reset the password.'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Reset password"
    >
      <div className="relative w-full max-w-md rounded-3xl border border-[var(--border)] bg-[var(--card)] p-8 shadow-xl">
        <button
          type="button"
          onClick={onCancel}
          aria-label="Close"
          className="absolute right-5 top-5 text-[var(--text-muted)] hover:text-[var(--text)]"
        >
          <X className="h-5 w-5" />
        </button>

        <h2 className="text-xl font-semibold text-[var(--text)]">Reset password</h2>
        <p className="mt-1 text-sm text-[var(--text-muted)]">
          {request.name} ({request.email}). {passwordHint} The user must change it at next login.
        </p>

        <div className="mt-5 space-y-4">
          <div>
            <label htmlFor="reset-password" className="mb-1.5 block text-xs font-medium tracking-wide text-[var(--text-muted)]">
              TEMPORARY PASSWORD
            </label>
            <input
              id="reset-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          <div>
            <label htmlFor="reset-confirm" className="mb-1.5 block text-xs font-medium tracking-wide text-[var(--text-muted)]">
              CONFIRM PASSWORD
            </label>
            <input
              id="reset-confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className={INPUT_CLASS}
            />
          </div>
          {password && confirm && password !== confirm && (
            <p className="text-xs text-red-500">Passwords do not match.</p>
          )}
        </div>

        {error && <p role="alert" className="mt-4 text-center text-sm text-red-500">{error}</p>}

        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-full border border-[#ffb100] px-8 py-2.5 text-sm font-medium text-[#ffb100] hover:bg-[#ffb100]/10"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={!valid || isSaving}
            className="rounded-full bg-[#ffb100] px-8 py-2.5 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving ? 'Saving…' : 'Reset password'}
          </button>
        </div>
      </div>
    </div>
  )
}
