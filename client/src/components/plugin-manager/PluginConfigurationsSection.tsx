import { useEffect, useState } from 'react'
import { CheckCircle2, Loader2, Plus, XCircle } from 'lucide-react'
import {
  applyPluginConfiguration,
  getConfigurationTargets,
  getPluginConfigurations,
} from '../../lib/pluginApi'
import { errorMessage } from '../../lib/api'
import { FAILED_STATUSES } from '../../types/plugin'
import type {
  PluginConfiguration,
  PluginConfigurationApplyResult,
  PluginConfigurationStatus,
  PluginDetails,
  PluginTarget,
} from '../../types/plugin'

type Props = {
  details: PluginDetails
  onChanged: () => Promise<void> | void
}

const STATUS_STYLES: Record<PluginConfigurationStatus, string> = {
  Applied: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  Pending: 'bg-gray-500/15 text-gray-600 dark:text-gray-300',
  Failed: 'bg-red-500/15 text-red-600 dark:text-red-400',
}

function targetLabel(target: PluginTarget) {
  return target.hostname ? `${target.hostname} (${target.ip_address})` : target.ip_address
}

export function PluginConfigurationsSection({ details, onChanged }: Props) {
  const [configurations, setConfigurations] = useState<PluginConfiguration[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [isFormOpen, setIsFormOpen] = useState(false)
  const [targets, setTargets] = useState<PluginTarget[] | null>(null)
  const [targetsError, setTargetsError] = useState<string | null>(null)
  const [targetId, setTargetId] = useState('')
  const [serviceDescription, setServiceDescription] = useState('')
  const [isApplying, setIsApplying] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [result, setResult] = useState<PluginConfigurationApplyResult | null>(null)

  // The backend refuses to configure a plugin that is failed or awaiting rollback.
  const isBlocked = FAILED_STATUSES.includes(details.status) || details.status === 'Rollback'

  async function loadConfigurations() {
    setLoadError(null)
    try {
      setConfigurations(await getPluginConfigurations(details.id))
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load monitoring targets.'))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    getPluginConfigurations(details.id)
      .then((data) => {
        if (!cancelled) setConfigurations(data)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(errorMessage(err, 'Unable to load monitoring targets.'))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [details.id])

  const openForm = async () => {
    setIsFormOpen(true)
    setApplyError(null)
    setResult(null)
    if (targets !== null) return
    try {
      setTargets(await getConfigurationTargets())
    } catch (err) {
      setTargetsError(errorMessage(err, 'Unable to load devices.'))
    }
  }

  const handleApply = async () => {
    setIsApplying(true)
    setApplyError(null)
    setResult(null)
    try {
      const applied = await applyPluginConfiguration(details.id, {
        netDiscoveryId: Number(targetId),
        serviceDescription: serviceDescription.trim(),
      })
      setResult(applied)
      if (applied.success) {
        setTargetId('')
        setServiceDescription('')
        setIsFormOpen(false)
      }
      await loadConfigurations()
      await onChanged()
    } catch (err) {
      setApplyError(errorMessage(err, 'Unable to apply configuration.'))
    } finally {
      setIsApplying(false)
    }
  }

  const appliedCount = configurations.filter((c) => c.status === 'Applied').length
  const deviceCount = new Set(
    configurations.filter((c) => c.status === 'Applied' && c.target).map((c) => c.target!.id)
  ).size

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Monitoring Targets</h4>
        {!isFormOpen && !isBlocked && (
          <button
            type="button"
            onClick={openForm}
            className="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
          >
            <Plus className="h-3 w-3" /> Apply to Device
          </button>
        )}
      </div>

      {isBlocked && (
        <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
          This plugin can’t be applied to devices while it is in the “{details.status}” state.
        </p>
      )}

      {isFormOpen && (
        <div className="mb-3 space-y-2 rounded-xl border border-gray-200 p-3 dark:border-white/10">
          {targetsError ? (
            <p className="text-xs text-red-600 dark:text-red-400">{targetsError}</p>
          ) : targets === null ? (
            <p className="flex items-center text-xs text-gray-500 dark:text-gray-400">
              <Loader2 className="mr-2 h-3 w-3 animate-spin" /> Loading devices…
            </p>
          ) : targets.length === 0 ? (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              No discovered devices yet. Run a network scan first.
            </p>
          ) : (
            <label className="block text-xs text-gray-500 dark:text-gray-400">
              Device
              <select
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 outline-none focus:border-gray-500 dark:border-white/20 dark:bg-[#0D1117] dark:text-white"
              >
                <option value="">Select a device…</option>
                {targets.map((target) => (
                  <option key={target.id} value={target.id}>
                    {targetLabel(target)}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block text-xs text-gray-500 dark:text-gray-400">
            Service name
            <input
              type="text"
              value={serviceDescription}
              onChange={(e) => setServiceDescription(e.target.value)}
              placeholder="e.g. Interface Traffic"
              className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 outline-none focus:border-gray-500 dark:border-white/20 dark:bg-[#0D1117] dark:text-white"
            />
          </label>

          {applyError && <p className="text-xs text-red-600 dark:text-red-400">{applyError}</p>}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleApply}
              disabled={isApplying || !targetId || !serviceDescription.trim()}
              className="rounded-lg bg-[#ffb100] px-3 py-1 text-xs font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isApplying ? 'Applying…' : 'Apply'}
            </button>
            <button
              type="button"
              onClick={() => setIsFormOpen(false)}
              disabled={isApplying}
              className="rounded-lg border border-gray-300 px-3 py-1 text-xs text-gray-700 dark:border-white/20 dark:text-gray-300"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {result && (
        <div
          className={`mb-3 space-y-1 rounded-lg px-3 py-2 text-xs ${
            result.success
              ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300'
              : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300'
          }`}
        >
          <div className="flex items-center gap-2 font-medium">
            {result.success ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
            {result.success
              ? 'Applied. Nagios is now monitoring this service.'
              : 'Nagios rejected the configuration. Nothing live was changed.'}
          </div>
          {!result.success && result.validation_output && (
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap font-mono opacity-90">
              {result.validation_output}
            </pre>
          )}
        </div>
      )}

      {loadError ? (
        <p className="text-sm text-red-600 dark:text-red-400">{loadError}</p>
      ) : isLoading ? (
        <p className="flex items-center text-sm text-gray-500 dark:text-gray-400">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading…
        </p>
      ) : configurations.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">Not applied to any device yet.</p>
      ) : (
        <>
          <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
            Monitoring {appliedCount} {appliedCount === 1 ? 'service' : 'services'} on {deviceCount}{' '}
            {deviceCount === 1 ? 'device' : 'devices'}.
          </p>
          <ul className="space-y-1.5">
            {configurations.map((config) => (
              <li
                key={config.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-white/10"
              >
                <span className="min-w-0 text-gray-700 dark:text-gray-300">
                  <span className="block truncate font-medium">{config.service_description}</span>
                  <span className="block truncate text-xs text-gray-400">
                    {config.target ? targetLabel(config.target) : 'Device no longer exists'}
                  </span>
                </span>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[config.status]}`}
                >
                  {config.status}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
