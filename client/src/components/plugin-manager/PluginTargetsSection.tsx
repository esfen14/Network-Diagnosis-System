import { useEffect, useState } from 'react'
import { Loader2, Play } from 'lucide-react'
import { errorMessage } from '../../lib/api'
import { applyPluginConfiguration, getMonitoringTargets, getPluginConfigurations } from '../../lib/pluginApi'
import type { MonitoringTarget, PluginConfigurationItem, PluginStatus } from '../../types/plugin'

type Props = {
  pluginId: number
  pluginName: string
  pluginStatus: PluginStatus
  onApplied: () => void | Promise<void>
}

const STATUS_STYLES: Record<PluginConfigurationItem['status'], string> = {
  Applied: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  Pending: 'bg-gray-500/15 text-gray-600 dark:text-gray-300',
  Failed: 'bg-red-500/15 text-red-600 dark:text-red-400',
}

function targetLabel(target: MonitoringTarget | null) {
  if (!target) return 'Removed device'
  return target.hostname ? `${target.hostname} (${target.ip_address})` : target.ip_address
}

export function PluginTargetsSection({ pluginId, pluginName, pluginStatus, onApplied }: Props) {
  const [configurations, setConfigurations] = useState<PluginConfigurationItem[]>([])
  const [targets, setTargets] = useState<MonitoringTarget[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [targetId, setTargetId] = useState('')
  const [serviceDescription, setServiceDescription] = useState(pluginName)
  const [isApplying, setIsApplying] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [validationOutput, setValidationOutput] = useState<string | null>(null)

  const canApply = pluginStatus === 'Enabled' || pluginStatus === 'Active'

  function load() {
    return Promise.all([getPluginConfigurations(pluginId), getMonitoringTargets()])
      .then(([configs, devices]) => {
        setConfigurations(configs)
        setTargets(devices)
        setLoadError(null)
      })
      .catch((err) => setLoadError(errorMessage(err, 'Unable to load monitoring targets.')))
      .finally(() => setIsLoading(false))
  }

  useEffect(() => {
    void load()
  }, [pluginId])

  const handleApply = async () => {
    const description = serviceDescription.trim()
    if (!targetId || !description) return

    setIsApplying(true)
    setApplyError(null)
    setValidationOutput(null)
    try {
      const result = await applyPluginConfiguration(pluginId, Number(targetId), description)
      if (!result.success) {
        setApplyError('Nagios rejected the configuration, so nothing was changed.')
        setValidationOutput(result.validation_output ?? null)
      } else {
        setTargetId('')
      }
      await load()
      await onApplied()
    } catch (err) {
      setApplyError(errorMessage(err, 'Unable to apply the plugin.'))
    } finally {
      setIsApplying(false)
    }
  }

  return (
    <section>
      <h4 className="mb-1 text-sm font-semibold text-gray-900 dark:text-white">Monitoring Targets</h4>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        Apply this plugin to a device to start running it as a Nagios check.
      </p>

      {loadError && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
          {loadError}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center py-4 text-sm text-gray-500 dark:text-gray-400">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading targets…
        </div>
      ) : (
        <>
          {configurations.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Not applied to any device yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {configurations.map((config) => (
                <li
                  key={config.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-white/10"
                >
                  <span className="min-w-0 text-gray-700 dark:text-gray-300">
                    <span className="block truncate font-medium">{config.service_description || '—'}</span>
                    <span className="block truncate text-xs text-gray-400">{targetLabel(config.target)}</span>
                  </span>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[config.status]}`}>
                    {config.status}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 space-y-2 rounded-xl border border-gray-200 p-3 dark:border-white/10">
            {!canApply ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Enable this plugin to apply it to a device.
              </p>
            ) : targets.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                No devices available. Run a network discovery scan first.
              </p>
            ) : (
              <>
                <label className="block text-xs text-gray-500 dark:text-gray-400">
                  Device
                  <select
                    aria-label="Device"
                    value={targetId}
                    onChange={(e) => setTargetId(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-white/20 dark:bg-[#0D1117] dark:text-white"
                  >
                    <option value="">Select a device…</option>
                    {targets.map((target) => (
                      <option key={target.id} value={target.id}>
                        {targetLabel(target)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs text-gray-500 dark:text-gray-400">
                  Service name
                  <input
                    aria-label="Service name"
                    value={serviceDescription}
                    onChange={(e) => setServiceDescription(e.target.value)}
                    maxLength={200}
                    className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-white/20 dark:bg-[#0D1117] dark:text-white"
                  />
                </label>
                <button
                  type="button"
                  onClick={handleApply}
                  disabled={isApplying || !targetId || !serviceDescription.trim()}
                  className="flex items-center gap-2 rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isApplying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  Apply to Device
                </button>
              </>
            )}

            {applyError && (
              <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
                {applyError}
                {validationOutput && (
                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-xs opacity-90">{validationOutput}</pre>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
