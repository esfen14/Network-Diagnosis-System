import { useState } from 'react'

import { errorMessage } from '../../lib/api'
import { pauseDevice, resumeDevice } from '../../lib/deviceMonitoringApi'
import { useCurrentUser } from '../../contexts/CurrentUserContext'
import type { MonitoringState } from '../../types/host'
import {
  MONITORING_LABELS,
  MONITORING_REASONS,
  MONITORING_STYLES,
  canPauseOrResume,
} from './monitoringState'

type Props = {
  deviceId: number
  hostname: string
  state: MonitoringState
  // Called after the server accepted a change, so the drawer and the table can load again.
  onChanged: () => void
}

// The Monitoring section of the device drawer (spec files/Device_Inventory_Requirements.md,
// "Monitoring state"): the device's label with the reason, and Pause / Resume for users with
// system.hosts.edit.
export function DeviceMonitoringSection({ deviceId, hostname, state, onChanged }: Props) {
  const { hasPermission } = useCurrentUser()
  const canEdit = hasPermission('system.hosts.edit') && canPauseOrResume(state)
  const paused = state === 'paused'

  const [confirming, setConfirming] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function confirm() {
    setIsSaving(true)
    setError(null)
    setNotice(null)
    try {
      const result = paused ? await resumeDevice(deviceId) : await pauseDevice(deviceId)
      setConfirming(false)
      if (result.config_ok === false) {
        setNotice(`The change was saved but Nagios was not updated: ${result.config_message}`)
      }
      onChanged()
    } catch (err) {
      setConfirming(false)
      setError(errorMessage(err, paused ? 'Unable to resume monitoring.' : 'Unable to pause monitoring.'))
    } finally {
      setIsSaving(false)
    }
  }

  const actionLabel = paused ? 'Resume monitoring' : 'Pause monitoring'

  return (
    <section>
      <h3 className="mb-2 font-semibold">Monitoring</h3>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${MONITORING_STYLES[state]}`}>
          {MONITORING_LABELS[state]}
        </span>
        {canEdit && (
          <button
            type="button"
            disabled={isSaving}
            onClick={() => setConfirming(true)}
            className="rounded-lg border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--text)] hover:bg-[var(--hover)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {actionLabel}
          </button>
        )}
      </div>
      <p className="mt-2 text-xs text-[var(--text-muted)]">{MONITORING_REASONS[state]}</p>

      {notice && (
        <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
          {notice}
        </p>
      )}
      {error && <p className="mt-2 text-xs text-red-600 dark:text-red-400">{error}</p>}

      {confirming && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Confirm ${actionLabel}`}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
        >
          <div className="w-full max-w-md space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-xl">
            <h3 className="text-base font-semibold text-[var(--text)]">{actionLabel}</h3>
            <p className="text-sm text-[var(--text-muted)]">
              {paused
                ? `Resume monitoring of ${hostname}? Nagios will start checking the device and its services again.`
                : `Pause monitoring of ${hostname}? Nagios will stop checking the device and all its services. Scans keep tracking it, and you can resume at any time.`}
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirming(false)}
                className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm text-[var(--text)] hover:bg-[var(--hover)]"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isSaving}
                onClick={confirm}
                className="rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? 'Saving…' : actionLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
