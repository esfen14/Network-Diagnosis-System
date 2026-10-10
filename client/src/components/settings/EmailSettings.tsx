import { useEffect, useState } from 'react'
import { AlertTriangle, ExternalLink, Loader2, Send } from 'lucide-react'

import { SettingsCard } from './SettingsCard'
import { SettingsActions } from './SettingsActions'
import { SettingsSelect } from './SettingsSelect'
import { errorMessage } from '../../lib/api'
import { getSmtpSettings, saveSmtpSettings, sendTestEmail } from '../../lib/smtpSettingsApi'
import type { SmtpPreset, SmtpSettings, SmtpTestResult } from '../../types/smtpSettings'

const PROVIDER_OPTIONS = [{ value: 'gmail', label: 'Gmail' }]

const APP_PASSWORDS_URL = 'https://myaccount.google.com/apppasswords'

const inputClass =
  'w-full rounded-xl border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--text)] outline-none focus:border-[#ffb100] disabled:opacity-60'

interface FormState {
  username: string
  sender: string
  // Only what was typed this session; the saved password is never loaded.
  password: string
}

function toForm(settings: SmtpSettings): FormState {
  return { username: settings.username, sender: settings.sender, password: '' }
}

export function EmailSettings() {
  const [saved, setSaved] = useState<SmtpSettings | null>(null)
  const [preset, setPreset] = useState<SmtpPreset | null>(null)
  const [form, setForm] = useState<FormState>({ username: '', sender: '', password: '' })
  // The sender follows the username until the admin types a different one.
  const [senderEdited, setSenderEdited] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<SmtpTestResult | null>(null)
  const [testError, setTestError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getSmtpSettings()
      .then((data) => {
        if (cancelled) return
        setSaved(data.settings)
        setPreset(data.presets.gmail)
        setForm(toForm(data.settings))
        setSenderEdited(data.settings.sender !== '' && data.settings.sender !== data.settings.username)
      })
      .catch((err) => { if (!cancelled) setLoadError(errorMessage(err, 'Unable to load email settings.')) })
    return () => { cancelled = true }
  }, [])

  if (loadError) {
    return (
      <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-4 text-sm text-red-500">{loadError}</div>
    )
  }
  if (!saved || !preset) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
        <Loader2 size={15} className="animate-spin" /> Loading email settings...
      </div>
    )
  }

  const senderDiffers = form.sender.trim() !== '' && form.sender.trim() !== form.username.trim()
  const hasChanges =
    form.username !== saved.username || form.sender !== saved.sender || form.password !== ''
  const canSave = form.username.trim() !== '' && (saved.passwordSet || form.password !== '')

  const setUsername = (username: string) =>
    setForm((current) => ({ ...current, username, sender: senderEdited ? current.sender : username }))

  const discard = () => {
    setForm(toForm(saved))
    setSenderEdited(saved.sender !== '' && saved.sender !== saved.username)
    setSaveError(null)
  }

  const save = async () => {
    if (!canSave) {
      setSaveError(saved.passwordSet ? 'Enter the Gmail address.' : 'Enter the Gmail address and the app password.')
      return
    }
    setIsSaving(true)
    setSaveError(null)
    try {
      const updated = await saveSmtpSettings(
        {
          username: form.username.trim(),
          sender: form.sender.trim() || form.username.trim(),
          // As typed or pasted, spaces included. Left out when blank so the saved one is kept.
          ...(form.password !== '' ? { password: form.password } : {}),
        },
        saved.version,
      )
      setSaved(updated)
      setForm(toForm(updated))
      setTestResult(null)
    } catch (err) {
      setSaveError(errorMessage(err, 'Unable to save email settings.'))
    } finally {
      setIsSaving(false)
    }
  }

  const runTest = async () => {
    setIsTesting(true)
    setTestResult(null)
    setTestError(null)
    try {
      setTestResult(await sendTestEmail())
    } catch (err) {
      setTestError(errorMessage(err, 'Unable to send the test email.'))
    } finally {
      setIsTesting(false)
    }
  }

  return (
    <div className="space-y-6">
      <SettingsCard
        title="Email (SMTP)"
        description="The Gmail account PinPoint sends notification email through. These settings are shared by the whole system: every alert email is sent from this one account, whoever is signed in."
      >
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-3">
            {/* Gmail is the only provider, so there is nothing to change yet. */}
            <SettingsSelect
              label="Provider"
              value={preset.provider}
              options={PROVIDER_OPTIONS}
              onChange={() => {}}
            />
            <label className="block text-sm text-[var(--text)]">
              Host
              <input aria-label="Host" value={preset.host} readOnly disabled className={`${inputClass} mt-1`} />
            </label>
            <div className="grid grid-cols-2 gap-4">
              <label className="block text-sm text-[var(--text)]">
                Port
                <input aria-label="Port" value={preset.port} readOnly disabled className={`${inputClass} mt-1`} />
              </label>
              <label className="block text-sm text-[var(--text)]">
                Security
                <input aria-label="Security" value="STARTTLS" readOnly disabled className={`${inputClass} mt-1`} />
              </label>
            </div>
          </div>

          <label className="block text-sm text-[var(--text)]">
            Username (full Gmail address)
            <input
              aria-label="Username"
              type="email"
              value={form.username}
              placeholder="you@gmail.com"
              autoComplete="off"
              onChange={(e) => setUsername(e.target.value)}
              className={`${inputClass} mt-1`}
            />
          </label>

          <div>
            <label className="block text-sm text-[var(--text)]">
              Sender
              <input
                aria-label="Sender"
                type="email"
                value={form.sender}
                autoComplete="off"
                onChange={(e) => { setSenderEdited(true); setForm({ ...form, sender: e.target.value }) }}
                className={`${inputClass} mt-1`}
              />
            </label>
            {senderDiffers && (
              <p role="alert" className="mt-1.5 flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-300">
                <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                Gmail rewrites the From address to the account you sign in with, so this sender will not be kept.
              </p>
            )}
          </div>

          <div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--hover)] p-3 text-xs text-[var(--text-muted)]">
              <p>
                Gmail does not accept your normal password here. Use a 16-character app password. You need 2-Step
                Verification turned on for the Google account to create one: Google Account → Security → App passwords.
              </p>
              <a
                href={APP_PASSWORDS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1.5 inline-flex items-center gap-1 text-[#ffb100] hover:underline"
              >
                Create an app password <ExternalLink size={12} />
              </a>
            </div>
            <label className="mt-3 block text-sm text-[var(--text)]">
              App password
              <input
                aria-label="App password"
                type="password"
                value={form.password}
                placeholder="xxxx xxxx xxxx xxxx"
                autoComplete="new-password"
                spellCheck={false}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className={`${inputClass} mt-1`}
              />
            </label>
            <p className="mt-1.5 text-xs text-[var(--text-muted)]">
              {saved.passwordSet
                ? 'An app password is saved. Leave this blank to keep it. '
                : ''}
              Paste it with or without spaces; it is used exactly as entered.
            </p>
          </div>

          <p className="text-xs text-[var(--text-muted)]">
            Gmail limits personal accounts to about 500 messages a day, and the appliance needs outbound access to
            smtp.gmail.com on port 587.
          </p>
        </div>

        <SettingsActions
          hasChanges={hasChanges}
          onSave={save}
          onDiscard={discard}
          isSaving={isSaving}
          saveError={saveError}
        />
      </SettingsCard>

      <SettingsCard
        title="Test email"
        description="Sends a message to your own address with the saved settings. Save any changes first."
      >
        <button
          type="button"
          onClick={runTest}
          disabled={!saved.configured || hasChanges || isTesting}
          className="flex items-center gap-2 rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm text-[var(--text)] transition hover:bg-[var(--hover)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isTesting ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          Send test email
        </button>

        {testError && <p role="alert" className="mt-3 text-sm text-red-500">{testError}</p>}

        {testResult?.ok && (
          <p role="status" className="mt-3 text-sm text-emerald-500">
            Test email sent to {testResult.recipient}. Did it arrive? Check that inbox (and spam). That is what
            confirms the address is yours; the app password only proves the login works.
          </p>
        )}

        {testResult && !testResult.ok && (
          <div role="alert" className="mt-3 text-sm text-red-500">
            <p>{testResult.message}</p>
            {(testResult.explanation || testResult.details) && (
              <details className="mt-1.5 text-xs text-[var(--text-muted)]">
                <summary className="cursor-pointer">Details</summary>
                {testResult.explanation && <p className="mt-1">{testResult.explanation}</p>}
                {testResult.details && (
                  <>
                    <p className="mt-2 font-medium">Server response</p>
                    <pre className="mt-0.5 whitespace-pre-wrap break-words">{testResult.details}</pre>
                  </>
                )}
              </details>
            )}
          </div>
        )}
      </SettingsCard>
    </div>
  )
}
