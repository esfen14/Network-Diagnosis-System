import { useEffect, useState, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, KeyRound, Loader2, Lock, Power, RotateCcw, ServerCog, X, XCircle } from 'lucide-react'
import { ApiError, errorMessage } from '../../lib/api'
import {
  checkCredentials,
  confirmTrust,
  getLiveFingerprint,
  NCPA_DEPLOYMENT_STARTED_EVENT,
  startDeployment,
} from '../../lib/ncpaDeploymentApi'
import type {
  CredentialCheckResult,
  DeviceCredentials,
  NcpaDevice,
  RejectedDevice,
  StartResult,
} from '../../types/ncpaDeployment'

export type WizardStep = 0 | 1 | 2 | 3

type Props = {
  devices: NcpaDevice[]
  // Devices to pre-select; null selects every deployable device.
  initialSelection: number[] | null
  startStep?: WizardStep
  // Only verify host keys (opened from a device's Verify button).
  verifyOnly?: boolean
  onClose: () => void
  onDevicesChanged: () => void
  onStarted: (result: StartResult) => void
}

type KeyState =
  | { state: 'loading' }
  | { state: 'shown'; fingerprint: string; changed?: boolean }
  | { state: 'trusting'; fingerprint: string }
  | { state: 'trusted'; fingerprint: string }
  | { state: 'skipped' }
  | { state: 'down' }
  | { state: 'error'; message: string }

type Login = { username: string; password: string }
type CheckState = CredentialCheckResult | 'checking'

const STEPS = ['Devices', 'Verify host keys', 'Credentials', 'Confirm']

const CHECK_TEXT: Record<CredentialCheckResult, string> = {
  ok: 'Login and sudo verified.',
  auth_failed: 'Rejected this username or password. Enter the login for this device.',
  no_sudo: 'Logged in, but this account cannot use sudo.',
  unreachable: 'Could not reach this device on port 22.',
  host_key_changed: 'Its host key changed. Remove it, then verify the key again from the Devices table.',
  not_trusted: 'Its host key is not trusted yet.',
  not_found: 'This device is no longer available.',
  rate_limited: 'Checked moments ago. Try again in a few seconds.',
}

// Results that need a different login for this device.
const NEEDS_OWN_LOGIN: CredentialCheckResult[] = ['auth_failed', 'no_sudo']
// Results a new login cannot fix; the device can only be removed.
const REMOVABLE: CredentialCheckResult[] = ['unreachable', 'host_key_changed', 'not_trusted', 'not_found']

const INPUT =
  'w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 outline-none focus:border-[#ffb100] dark:border-white/10 dark:bg-[#0D1117] dark:text-white'
const BUTTON_SM =
  'inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-default disabled:opacity-50 dark:border-white/10 dark:text-gray-200 dark:hover:bg-white/10'
const BUTTON_PRIMARY =
  'inline-flex items-center gap-2 rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-gray-900 hover:bg-[#f0a500] disabled:cursor-default disabled:opacity-50'
const BUTTON =
  'rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-200 dark:hover:bg-white/10'

export function DeployWizard({
  devices,
  initialSelection,
  startStep = 0,
  verifyOnly = false,
  onClose,
  onDevicesChanged,
  onStarted,
}: Props) {
  const pool = devices.filter((d) => d.deployable)
  const [step, setStep] = useState<WizardStep>(startStep)
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set((initialSelection ?? pool.map((d) => d.id)).filter((id) => pool.some((d) => d.id === id))),
  )
  const [keys, setKeys] = useState<Record<number, KeyState>>({})
  const [shared, setShared] = useState<Login>({ username: '', password: '' })
  const [own, setOwn] = useState<Set<number>>(new Set())
  const [perDevice, setPerDevice] = useState<Record<number, Login>>({})
  const [checks, setChecks] = useState<Record<number, CheckState>>({})
  const [removed, setRemoved] = useState<Record<number, string>>({})
  const [checkError, setCheckError] = useState<string | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [rejected, setRejected] = useState<RejectedDevice[]>([])
  const [isStarting, setIsStarting] = useState(false)

  const chosen = pool.filter((d) => selected.has(d.id))
  const isTrusted = (d: NcpaDevice) => d.trusted || keys[d.id]?.state === 'trusted'
  const deployList = chosen.filter(isTrusted)
  const loginFor = (id: number): Login => (own.has(id) ? perDevice[id] ?? { username: '', password: '' } : shared)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // ── Step 2: host keys ──────────────────────────────────────────────────────

  const fetchKey = async (device: NcpaDevice) => {
    setKeys((prev) => ({ ...prev, [device.id]: { state: 'loading' } }))
    try {
      const fingerprint = await getLiveFingerprint(device.id)
      setKeys((prev) => ({ ...prev, [device.id]: { state: 'shown', fingerprint } }))
    } catch (err) {
      const next: KeyState =
        err instanceof ApiError && err.status === 502
          ? { state: 'down' }
          : { state: 'error', message: errorMessage(err, 'Could not read the host key.') }
      setKeys((prev) => ({ ...prev, [device.id]: next }))
    }
  }

  // Fetch every key still unknown whenever the verify step is shown.
  useEffect(() => {
    if (step !== 1) return
    chosen.filter((d) => !d.trusted && !keys[d.id]).forEach(fetchKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  const trust = async (device: NcpaDevice, fingerprint: string) => {
    setKeys((prev) => ({ ...prev, [device.id]: { state: 'trusting', fingerprint } }))
    try {
      await confirmTrust(device.id, fingerprint)
      setKeys((prev) => ({ ...prev, [device.id]: { state: 'trusted', fingerprint } }))
      onDevicesChanged()
    } catch (err) {
      let next: KeyState = { state: 'error', message: errorMessage(err, 'Could not save the host key.') }
      if (err instanceof ApiError && err.status === 409) {
        const live = (err.data as { fingerprint?: string } | undefined)?.fingerprint
        if (live) next = { state: 'shown', fingerprint: live, changed: true }
      } else if (err instanceof ApiError && err.status === 502) {
        next = { state: 'down' }
      }
      setKeys((prev) => ({ ...prev, [device.id]: next }))
    }
  }

  const verifyBlocking = chosen.some((d) => {
    if (isTrusted(d)) return false
    const k = keys[d.id]
    return !k || k.state === 'loading' || k.state === 'shown' || k.state === 'trusting' || k.state === 'error'
  })

  // ── Step 3: credentials ────────────────────────────────────────────────────

  const credsReady = deployList.every((d) => {
    const login = loginFor(d.id)
    return login.username.trim() !== '' && login.password !== ''
  })
  const isChecking = deployList.some((d) => checks[d.id] === 'checking')
  const allVerified = deployList.length > 0 && deployList.every((d) => checks[d.id] === 'ok')
  const problems = deployList.filter((d) => {
    const c = checks[d.id]
    return c !== undefined && c !== 'ok' && c !== 'checking'
  })

  const clearChecks = (ids: number[]) =>
    setChecks((prev) => {
      const next = { ...prev }
      ids.forEach((id) => delete next[id])
      return next
    })

  const editShared = (patch: Partial<Login>) => {
    setShared((prev) => ({ ...prev, ...patch }))
    clearChecks(deployList.filter((d) => !own.has(d.id)).map((d) => d.id))
  }

  const editOwn = (id: number, patch: Partial<Login>) => {
    setPerDevice((prev) => ({ ...prev, [id]: { ...(prev[id] ?? { username: '', password: '' }), ...patch } }))
    clearChecks([id])
  }

  const setOwnLogin = (id: number, on: boolean) => {
    setOwn((prev) => {
      const next = new Set(prev)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })
    clearChecks([id])
  }

  const removeDevice = (id: number, reason: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.delete(id)
      return next
    })
    setRemoved((prev) => ({ ...prev, [id]: reason }))
    clearChecks([id])
  }

  const runCheck = async () => {
    const toCheck = deployList.filter((d) => checks[d.id] !== 'ok')
    setCheckError(null)
    setChecks((prev) => ({ ...prev, ...Object.fromEntries(toCheck.map((d) => [d.id, 'checking' as const])) }))
    try {
      const results = await checkCredentials(
        toCheck.map((d) => ({ deviceId: d.id, ...loginFor(d.id) })),
      )
      const failedLogins = results.filter((r) => NEEDS_OWN_LOGIN.includes(r.result)).map((r) => r.deviceId)
      setChecks((prev) => ({ ...prev, ...Object.fromEntries(results.map((r) => [r.deviceId, r.result])) }))
      if (failedLogins.length) {
        setOwn((prev) => new Set([...prev, ...failedLogins]))
        setPerDevice((prev) => {
          const next = { ...prev }
          failedLogins.forEach((id) => {
            next[id] = { username: next[id]?.username ?? '', password: '' }
          })
          return next
        })
        window.setTimeout(() => focusDevice(failedLogins[0]), 0)
      }
    } catch (err) {
      clearChecks(toCheck.map((d) => d.id))
      setCheckError(errorMessage(err, 'Could not check the logins.'))
    }
  }

  const focusDevice = (id: number) => {
    document.getElementById(`ncpa-login-row-${id}`)?.scrollIntoView({ block: 'center' })
    document.getElementById(`ncpa-username-${id}`)?.focus({ preventScroll: true })
  }

  // ── Step 4: start ──────────────────────────────────────────────────────────

  const deploy = async () => {
    setIsStarting(true)
    setStartError(null)
    setRejected([])
    const entries: DeviceCredentials[] = deployList.map((d) => ({ deviceId: d.id, ...loginFor(d.id) }))
    try {
      const result = await startDeployment(entries)
      // Drop the passwords as soon as the server has them.
      setShared((prev) => ({ ...prev, password: '' }))
      setPerDevice({})
      window.dispatchEvent(new CustomEvent(NCPA_DEPLOYMENT_STARTED_EVENT))
      onStarted(result)
    } catch (err) {
      const reasons = err instanceof ApiError ? (err.data as { rejected?: RejectedDevice[] } | undefined)?.rejected : undefined
      if (reasons?.length) setRejected(reasons)
      setStartError(errorMessage(err, 'Could not start the deployment.'))
      setIsStarting(false)
    }
  }

  // ── Navigation ─────────────────────────────────────────────────────────────

  let canNext = true
  let nextLabel = 'Next'
  if (step === 0) canNext = selected.size > 0
  if (step === 1) {
    canNext = !verifyBlocking && (verifyOnly || deployList.length > 0)
    if (verifyOnly) nextLabel = 'Done'
  }
  if (step === 2) {
    canNext = credsReady && !isChecking && deployList.length > 0
    nextLabel = allVerified ? 'Next' : isChecking ? 'Checking…' : 'Check logins'
  }
  if (step === 3) {
    canNext = !isStarting && deployList.length > 0
    nextLabel = isStarting ? 'Starting…' : 'Deploy NCPA'
  }

  const next = () => {
    if (verifyOnly && step === 1) return onClose()
    if (step === 2 && !allVerified) return void runCheck()
    if (step === 3) return void deploy()
    setStep((s) => (s + 1) as WizardStep)
  }
  const back = () => {
    if (step === 0 || verifyOnly) return onClose()
    setStep((s) => (s - 1) as WizardStep)
  }

  const nameOf = (id: number) => devices.find((d) => d.id === id)?.hostname ?? `Device ${id}`

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto overscroll-contain bg-black/60 p-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="ncpa-wizard-title"
        className="my-auto w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl dark:bg-[#171B20]"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="ncpa-wizard-title" className="text-lg font-semibold text-gray-900 dark:text-white">
              {verifyOnly ? 'Verify host key' : 'Deploy NCPA'}
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {verifyOnly
                ? "Confirm this device's SSH host key so NCPA can be deployed to it."
                : 'Select devices, verify host keys, check logins, then deploy.'}
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
            <X className="h-5 w-5" />
          </button>
        </div>

        {!verifyOnly && (
          <ol className="mt-5 grid grid-cols-4 gap-2 text-xs">
            {STEPS.map((name, i) => (
              <li
                key={name}
                aria-current={i === step ? 'step' : undefined}
                className={`flex flex-col gap-1.5 ${i <= step ? 'text-gray-900 dark:text-white' : 'text-gray-400'} ${i === step ? 'font-semibold' : ''}`}
              >
                <span className={`h-1 rounded-full ${i <= step ? 'bg-[#ffb100]' : 'bg-gray-200 dark:bg-white/10'}`} />
                {i + 1}. {name}
              </li>
            ))}
          </ol>
        )}

        <div className="mt-5 space-y-4">
          {step === 0 && (
            <>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Choose the devices to deploy to. Only devices whose agent is pending or failed are listed.
              </p>
              {pool.length === 0 ? (
                <p className="rounded-lg bg-gray-50 px-4 py-6 text-center text-sm text-gray-500 dark:bg-white/5">
                  No devices are waiting for NCPA.
                </p>
              ) : (
                <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200 dark:divide-white/5 dark:border-white/10">
                  {pool.map((d) => (
                    <li key={d.id}>
                      <label className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-white/5">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-[#ffb100]"
                          checked={selected.has(d.id)}
                          onChange={(e) =>
                            setSelected((prev) => {
                              const next = new Set(prev)
                              if (e.target.checked) next.add(d.id)
                              else next.delete(d.id)
                              return next
                            })
                          }
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block text-sm font-medium text-gray-900 dark:text-white">{d.hostname}</span>
                          <span className="block text-xs text-gray-500 dark:text-gray-400">
                            {d.ipAddress}
                            {d.lastError ? ` · last run: ${d.lastError}` : ''}
                          </span>
                        </span>
                        <TrustLabel trusted={isTrusted(d)} />
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          {step === 1 && (
            <>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Compare each fingerprint with the device&apos;s own SSH host key before you trust it. Pinpoint only
                connects to devices whose key matches the one you trust here.
              </p>
              <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200 dark:divide-white/5 dark:border-white/10">
                {chosen.map((d) => (
                  <KeyRow key={d.id} device={d} keyState={keys[d.id]} onTrust={trust} onRetry={fetchKey}
                    onSkip={(id) => setKeys((prev) => ({ ...prev, [id]: { state: 'skipped' } }))} />
                ))}
              </ul>
            </>
          )}

          {step === 2 && (
            <>
              {problems.length > 0 && (
                <div role="alert" className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    <b>{problems.length} device{problems.length > 1 ? 's need' : ' needs'} attention:</b>{' '}
                    {problems.map((d, i) => (
                      <span key={d.id}>
                        {i > 0 && ', '}
                        <button type="button" className="font-semibold underline underline-offset-2" onClick={() => focusDevice(d.id)}>
                          {d.hostname}
                        </button>
                      </span>
                    ))}
                    . They are listed first.
                  </span>
                </div>
              )}
              {checkError && <ErrorBox message={checkError} />}

              {deployList.some((d) => !own.has(d.id)) && (
                <fieldset className="space-y-2">
                  <legend className="text-sm font-semibold text-gray-900 dark:text-white">
                    {deployList.length === 1 ? (
                      <>Credentials for {deployList[0].hostname} <span className="font-normal text-gray-500">· {deployList[0].ipAddress}</span></>
                    ) : (
                      <>Shared credentials <span className="font-normal text-gray-500">· used for every device without its own login</span></>
                    )}
                  </legend>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field id="ncpa-shared-username" label="SSH username" value={shared.username} onChange={(v) => editShared({ username: v })} />
                    <Field id="ncpa-shared-password" label="Password" type="password" value={shared.password} onChange={(v) => editShared({ password: v })} />
                  </div>
                </fieldset>
              )}

              <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200 dark:divide-white/5 dark:border-white/10">
                {[...problems, ...deployList.filter((d) => !problems.includes(d))].map((d) => {
                  const check = checks[d.id]
                  const hasOwn = own.has(d.id)
                  const flagged = check === 'auth_failed' || check === 'no_sudo'
                  return (
                    <li
                      key={d.id}
                      id={`ncpa-login-row-${d.id}`}
                      className={`scroll-my-24 px-4 py-3 ${flagged ? 'bg-red-50 dark:bg-red-500/10' : check && REMOVABLE.includes(check as CredentialCheckResult) ? 'bg-gray-50 dark:bg-white/5' : ''}`}
                    >
                      <div className="flex flex-wrap items-center gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-gray-900 dark:text-white">
                            {d.hostname} <span className="font-normal text-gray-500">· {d.ipAddress}</span>
                          </p>
                          <CheckLine check={check} hasOwn={hasOwn} />
                        </div>
                        {!isChecking && (
                          check && REMOVABLE.includes(check as CredentialCheckResult) ? (
                            <button type="button" className={BUTTON_SM} onClick={() => removeDevice(d.id, CHECK_TEXT[check as CredentialCheckResult])}>Remove</button>
                          ) : hasOwn ? (
                            deployList.length > 1 && <button type="button" className={BUTTON_SM} onClick={() => setOwnLogin(d.id, false)}>Use shared login</button>
                          ) : (
                            <button type="button" className={BUTTON_SM} onClick={() => setOwnLogin(d.id, true)}>Use a different login</button>
                          )
                        )}
                      </div>
                      {hasOwn && !(check && REMOVABLE.includes(check as CredentialCheckResult)) && (
                        <div className="mt-3 grid gap-3 sm:grid-cols-2">
                          <Field id={`ncpa-username-${d.id}`} label={`Username for ${d.hostname}`} value={loginFor(d.id).username} onChange={(v) => editOwn(d.id, { username: v })} />
                          <Field id={`ncpa-password-${d.id}`} label={`Password for ${d.hostname}`} type="password" value={loginFor(d.id).password} onChange={(v) => editOwn(d.id, { password: v })} />
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>

              <p className="flex gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-500 dark:bg-white/5 dark:text-gray-400">
                <Lock className="mt-0.5 h-4 w-4 shrink-0" />
                Each account needs sudo rights. Pinpoint tests each login first, then uses it once to create a
                restricted <code className="font-mono text-xs">pinpoint-deployment</code> account with an SSH key.
                Passwords are not stored.
              </p>
            </>
          )}

          {step === 3 && (
            <>
              <p className="text-sm text-gray-700 dark:text-gray-300">
                Deploy NCPA to <b>{deployList.length} device{deployList.length === 1 ? '' : 's'}</b>. Host keys are
                trusted and every login was verified.
              </p>
              <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200 dark:divide-white/5 dark:border-white/10">
                {deployList.map((d) => (
                  <li key={d.id} className="flex items-center gap-3 px-4 py-3">
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium text-gray-900 dark:text-white">{d.hostname}</span>
                      <span className="block text-xs text-gray-500 dark:text-gray-400">
                        {d.ipAddress} · logs in as {loginFor(d.id).username}
                        {own.has(d.id) ? ' (own login)' : ''}
                      </span>
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="h-4 w-4" /> Ready
                    </span>
                  </li>
                ))}
              </ul>
              <LeftOut chosen={chosen} isTrusted={isTrusted} keys={keys} removed={removed} nameOf={nameOf} />
              {startError && <ErrorBox message={startError} />}
              {rejected.length > 0 && (
                <ul className="list-inside list-disc text-sm text-red-700 dark:text-red-300">
                  {rejected.map((r) => (
                    <li key={r.device_id}>{nameOf(r.device_id)}: {r.reason}</li>
                  ))}
                </ul>
              )}
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Each device takes about a minute. You can leave this page; progress shows in the notification bell.
              </p>
            </>
          )}
        </div>

        <div className="sticky bottom-0 -mx-6 -mb-6 mt-6 flex flex-wrap justify-between gap-2 rounded-b-2xl border-t border-gray-200 bg-white px-6 py-4 dark:border-white/10 dark:bg-[#171B20]">
          <button type="button" onClick={back} className={BUTTON}>
            {step === 0 || verifyOnly ? 'Cancel' : 'Back'}
          </button>
          <button type="button" onClick={next} disabled={!canNext} className={BUTTON_PRIMARY}>
            {step === 3 && <ServerCog className="h-4 w-4" />}
            {nextLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

function TrustLabel({ trusted }: { trusted: boolean }) {
  return trusted ? (
    <span className="inline-flex shrink-0 items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
      <CheckCircle2 className="h-4 w-4" /> Trusted
    </span>
  ) : (
    <span className="inline-flex shrink-0 items-center gap-1 text-xs text-amber-600 dark:text-amber-400">
      <AlertTriangle className="h-4 w-4" /> Not verified
    </span>
  )
}

function KeyRow({
  device,
  keyState,
  onTrust,
  onRetry,
  onSkip,
}: {
  device: NcpaDevice
  keyState: KeyState | undefined
  onTrust: (device: NcpaDevice, fingerprint: string) => void
  onRetry: (device: NcpaDevice) => void
  onSkip: (id: number) => void
}) {
  let detail: ReactNode
  let actions: ReactNode
  const fingerprint = (value: string) => (
    <code className="mt-1 block break-all rounded-md border border-gray-200 bg-gray-50 px-2 py-1 font-mono text-xs text-gray-900 dark:border-white/10 dark:bg-[#0D1117] dark:text-white">
      SHA256:{value}
    </code>
  )

  if (device.trusted) {
    detail = device.fingerprint ? fingerprint(device.fingerprint) : null
    actions = <TrustLabel trusted />
  } else if (!keyState || keyState.state === 'loading') {
    detail = <span className="text-xs text-gray-500">Contacting {device.ipAddress} on port 22…</span>
    actions = <Loader2 className="h-4 w-4 animate-spin text-gray-400" aria-label="Loading" />
  } else if (keyState.state === 'shown' || keyState.state === 'trusting') {
    detail = (
      <>
        {keyState.state === 'shown' && keyState.changed && (
          <span className="block text-xs font-medium text-amber-700 dark:text-amber-300">
            The key changed while you were looking. Compare the new key before trusting it.
          </span>
        )}
        {fingerprint(keyState.fingerprint)}
      </>
    )
    actions = (
      <span className="flex gap-1.5">
        <button type="button" className={BUTTON_SM} disabled={keyState.state === 'trusting'} onClick={() => onSkip(device.id)}>Skip</button>
        <button
          type="button"
          className={`${BUTTON_SM} border-[#ffb100] bg-[#ffb100] text-gray-900 hover:bg-[#f0a500] dark:text-gray-900`}
          disabled={keyState.state === 'trusting'}
          onClick={() => onTrust(device, keyState.fingerprint)}
        >
          <KeyRound className="h-3.5 w-3.5" />
          {keyState.state === 'trusting' ? 'Trusting…' : 'Trust'}
        </button>
      </span>
    )
  } else if (keyState.state === 'trusted') {
    detail = fingerprint(keyState.fingerprint)
    actions = <TrustLabel trusted />
  } else if (keyState.state === 'skipped') {
    detail = <span className="text-xs text-gray-500">Skipped. This device won&apos;t be deployed.</span>
    actions = <button type="button" className={BUTTON_SM} onClick={() => onRetry(device)}>Undo</button>
  } else if (keyState.state === 'down') {
    detail = (
      <span className="text-xs text-gray-500">
        Could not reach {device.ipAddress} on port 22. Check the device is on and SSH is running.
      </span>
    )
    actions = (
      <span className="flex items-center gap-1.5">
        <span className="inline-flex items-center gap-1 text-xs text-gray-500"><Power className="h-3.5 w-3.5" /> Down</span>
        <button type="button" className={BUTTON_SM} onClick={() => onRetry(device)}><RotateCcw className="h-3.5 w-3.5" /> Retry</button>
      </span>
    )
  } else {
    detail = <span className="text-xs text-red-600 dark:text-red-400">{keyState.message}</span>
    actions = (
      <span className="flex gap-1.5">
        <button type="button" className={BUTTON_SM} onClick={() => onSkip(device.id)}>Skip</button>
        <button type="button" className={BUTTON_SM} onClick={() => onRetry(device)}><RotateCcw className="h-3.5 w-3.5" /> Retry</button>
      </span>
    )
  }

  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gray-900 dark:text-white">
          {device.hostname} <span className="font-normal text-gray-500">· {device.ipAddress}</span>
        </p>
        {detail}
      </div>
      {actions}
    </li>
  )
}

function CheckLine({ check, hasOwn }: { check: CheckState | undefined; hasOwn: boolean }) {
  if (!check) {
    return <p className="text-xs text-gray-500">{hasOwn ? 'Uses its own login' : 'Uses the shared login'}</p>
  }
  if (check === 'checking') {
    return (
      <p className="flex items-center gap-1.5 text-xs text-gray-500">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Checking login…
      </p>
    )
  }
  const tone =
    check === 'ok'
      ? 'text-emerald-600 dark:text-emerald-400'
      : NEEDS_OWN_LOGIN.includes(check)
        ? 'text-red-600 dark:text-red-400'
        : 'text-gray-600 dark:text-gray-400'
  const Icon = check === 'ok' ? CheckCircle2 : check === 'unreachable' ? Power : XCircle
  return (
    <p className={`flex items-center gap-1.5 text-xs ${tone}`}>
      <Icon className="h-3.5 w-3.5 shrink-0" /> {CHECK_TEXT[check]}
    </p>
  )
}

function LeftOut({
  chosen,
  isTrusted,
  keys,
  removed,
  nameOf,
}: {
  chosen: NcpaDevice[]
  isTrusted: (d: NcpaDevice) => boolean
  keys: Record<number, KeyState>
  removed: Record<number, string>
  nameOf: (id: number) => string
}) {
  const reasons = [
    ...chosen
      .filter((d) => !isTrusted(d))
      .map((d) => `${d.hostname} (${keys[d.id]?.state === 'down' ? 'down' : 'host key not trusted'})`),
    ...Object.entries(removed).map(([id]) => `${nameOf(Number(id))} (removed)`),
  ]
  if (reasons.length === 0) return null
  return (
    <p className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>Not included: {reasons.join(', ')}.</span>
    </p>
  )
}

function Field({
  id,
  label,
  value,
  onChange,
  type = 'text',
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  type?: 'text' | 'password'
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
      </label>
      <input
        id={id}
        type={type}
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={INPUT}
      />
    </div>
  )
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
      {message}
    </div>
  )
}
