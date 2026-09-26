import { useEffect, useState } from 'react'
import {
  CheckCircle2,
  Loader2,
  Pencil,
  Power,
  PowerOff,
  RotateCcw,
  ShieldCheck,
  X,
  XCircle,
} from 'lucide-react'
import {
  disablePlugin,
  enablePlugin,
  getPluginCommands,
  getPluginDependencies,
  getPluginDetails,
  overrideCommand,
  restoreDefaultCommand,
  validatePlugin,
} from '../../lib/pluginApi'
import { errorMessage } from '../../lib/api'
import { PluginConfigurationsSection } from './PluginConfigurationsSection'
import { PluginUpdateSection } from './PluginUpdateSection'
import type { PluginCommand, PluginDependency, PluginDetails, PluginValidationResult } from '../../types/plugin'

type Props = {
  pluginId: number
  onClose: () => void
  onChanged: () => void
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

const DEPENDENCY_STYLES: Record<PluginDependency['status'], string> = {
  Ok: 'text-emerald-600 dark:text-emerald-400',
  Missing: 'text-red-600 dark:text-red-400',
  Incompatible: 'text-amber-600 dark:text-amber-400',
}

export function PluginDetailsDrawer({ pluginId, onClose, onChanged }: Props) {
  const [details, setDetails] = useState<PluginDetails | null>(null)
  const [commands, setCommands] = useState<PluginCommand[]>([])
  const [dependencies, setDependencies] = useState<PluginDependency[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [isBusy, setIsBusy] = useState(false)
  const [validation, setValidation] = useState<PluginValidationResult | null>(null)
  const [editingCommandId, setEditingCommandId] = useState<number | null>(null)
  const [overrideValue, setOverrideValue] = useState('')

  // silent skips the loading spinner so child sections keep their state
  // (e.g. an update result message) while the details refresh.
  async function load(silent = false) {
    if (!silent) setIsLoading(true)
    setLoadError(null)
    try {
      const [d, c, deps] = await Promise.all([
        getPluginDetails(pluginId),
        getPluginCommands(pluginId),
        getPluginDependencies(pluginId),
      ])
      setDetails(d)
      setCommands(c)
      setDependencies(deps)
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load plugin details.'))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pluginId])

  const runAction = async (action: () => Promise<void>) => {
    setIsBusy(true)
    setActionError(null)
    try {
      await action()
      await load()
      onChanged()
    } catch (err) {
      setActionError(errorMessage(err, 'Action failed.'))
    } finally {
      setIsBusy(false)
    }
  }

  const refreshAfterChildAction = async () => {
    await load(true)
    onChanged()
  }

  const handleEnable = () => runAction(async () => { await enablePlugin(pluginId) })
  const handleDisable = () => runAction(async () => { await disablePlugin(pluginId) })

  const handleValidate = () =>
    runAction(async () => {
      setValidation(await validatePlugin(pluginId))
    })

  const startOverride = (command: PluginCommand) => {
    setEditingCommandId(command.id)
    setOverrideValue(command.active_command)
  }

  const saveOverride = (commandId: number) =>
    runAction(async () => {
      await overrideCommand(pluginId, commandId, overrideValue)
      setEditingCommandId(null)
    })

  const restoreDefault = (commandId: number) =>
    runAction(async () => { await restoreDefaultCommand(pluginId, commandId) })

  const canEnable = details ? !details.status.endsWith('Failed') && details.status !== 'Rollback' && details.status !== 'Active' && details.status !== 'Enabled' : false
  const canDisable = details ? details.status === 'Enabled' || details.status === 'Active' : false

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <div className="h-full w-full max-w-xl overflow-y-auto bg-white shadow-xl dark:bg-[#171B20]">
        <div className="sticky top-0 flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4 dark:border-white/10 dark:bg-[#171B20]">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Plugin Details
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-6 p-6">
          {loadError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
              {loadError}
            </div>
          )}
          {actionError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
              {actionError}
            </div>
          )}

          {isLoading ? (
            <div className="flex items-center justify-center py-16 text-gray-500 dark:text-gray-400">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading…
            </div>
          ) : details ? (
            <>
              <section>
                <h3 className="text-xl font-semibold text-gray-900 dark:text-white">
                  {details.display_name || details.name}
                </h3>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  {details.description || 'No description available.'}
                </p>

                <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <dt className="text-gray-400">Status</dt>
                    <dd className="font-medium text-gray-900 dark:text-white">{details.status}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-400">Version</dt>
                    <dd className="font-medium text-gray-900 dark:text-white">{details.current_version ?? '—'}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-400">Type</dt>
                    <dd className="font-medium text-gray-900 dark:text-white">{details.type}</dd>
                  </div>
                  <div>
                    <dt className="text-gray-400">Source</dt>
                    <dd className="font-medium text-gray-900 dark:text-white">{details.source}</dd>
                  </div>
                  <div className="col-span-2">
                    <dt className="text-gray-400">Executable Path</dt>
                    <dd className="break-all font-mono text-xs text-gray-700 dark:text-gray-300">
                      {details.executable_path}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-gray-400">Updated</dt>
                    <dd className="text-gray-700 dark:text-gray-300">{formatDateTime(details.updated_at)}</dd>
                  </div>
                </dl>

                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={handleEnable}
                    disabled={isBusy || !canEnable}
                    className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Power className="h-4 w-4" /> Enable
                  </button>
                  <button
                    type="button"
                    onClick={handleDisable}
                    disabled={isBusy || !canDisable}
                    className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
                  >
                    <PowerOff className="h-4 w-4" /> Disable
                  </button>
                  <button
                    type="button"
                    onClick={handleValidate}
                    disabled={isBusy}
                    className="flex items-center gap-2 rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <ShieldCheck className="h-4 w-4" /> Validate
                  </button>
                </div>

                {validation && (
                  <div
                    className={`mt-3 space-y-1.5 rounded-lg px-3 py-2 text-sm ${
                      validation.is_valid
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300'
                        : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300'
                    }`}
                  >
                    <div className="flex items-center gap-2 font-medium">
                      {validation.is_valid ? (
                        <CheckCircle2 className="h-4 w-4" />
                      ) : (
                        <XCircle className="h-4 w-4" />
                      )}
                      {validation.is_valid ? 'Validation passed.' : 'Validation failed.'}
                    </div>
                    <ul className="space-y-0.5 pl-6 text-xs opacity-90">
                      {Object.entries(validation.checks).map(([name, check]) => (
                        <li key={name}>
                          {check.passed ? '✓' : '✗'} {name}: {check.message}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>

              <PluginConfigurationsSection details={details} onChanged={refreshAfterChildAction} />

              <PluginUpdateSection details={details} onChanged={refreshAfterChildAction} />

              <section>
                <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">
                  Commands
                </h4>
                <div className="space-y-2">
                  {commands.length === 0 && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">No commands defined.</p>
                  )}
                  {commands.map((command) => (
                    <div
                      key={command.id}
                      className="rounded-xl border border-gray-200 p-3 dark:border-white/10"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-900 dark:text-white">
                          {command.command_name}
                        </span>
                        {command.is_overridden && (
                          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400">
                            Overridden
                          </span>
                        )}
                      </div>

                      {editingCommandId === command.id ? (
                        <div className="mt-2 space-y-2">
                          <textarea
                            value={overrideValue}
                            onChange={(e) => setOverrideValue(e.target.value)}
                            rows={2}
                            className="w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 font-mono text-xs text-gray-900 outline-none focus:border-gray-500 dark:border-white/20 dark:bg-[#0D1117] dark:text-white"
                          />
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => saveOverride(command.id)}
                              disabled={isBusy}
                              className="rounded-lg bg-[#ffb100] px-3 py-1 text-xs font-semibold text-black"
                            >
                              Save Override
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingCommandId(null)}
                              className="rounded-lg border border-gray-300 px-3 py-1 text-xs text-gray-700 dark:border-white/20 dark:text-gray-300"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <p className="mt-1 break-all font-mono text-xs text-gray-600 dark:text-gray-300">
                            {command.active_command}
                          </p>
                          <div className="mt-2 flex gap-2">
                            <button
                              type="button"
                              onClick={() => startOverride(command)}
                              className="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
                            >
                              <Pencil className="h-3 w-3" /> Override
                            </button>
                            {command.is_overridden && (
                              <button
                                type="button"
                                onClick={() => restoreDefault(command.id)}
                                disabled={isBusy}
                                className="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
                              >
                                <RotateCcw className="h-3 w-3" /> Restore Default
                              </button>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">
                  Dependencies
                </h4>
                {dependencies.length === 0 ? (
                  <p className="text-sm text-gray-500 dark:text-gray-400">No dependencies recorded.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {dependencies.map((dep) => (
                      <li
                        key={dep.id}
                        className="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-white/10"
                      >
                        <span className="text-gray-700 dark:text-gray-300">
                          {dep.name}{' '}
                          <span className="text-xs text-gray-400">
                            ({dep.type}{dep.required_version ? ` ≥ ${dep.required_version}` : ''})
                          </span>
                        </span>
                        <span className={`font-medium ${DEPENDENCY_STYLES[dep.status]}`}>
                          {dep.status}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}
