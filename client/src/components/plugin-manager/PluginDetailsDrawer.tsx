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
  getEnablePreview,
  getPluginCommands,
  getPluginDependencies,
  getPluginDetails,
  overrideCommand,
  restoreDefaultCommand,
  rollbackPluginUpdate,
  updatePlugin,
  validatePlugin,
  type PluginUpdateResult,
} from '../../lib/pluginApi'
import { errorMessage } from '../../lib/api'
import { useCurrentUser } from '../../contexts/CurrentUserContext'
import { PluginServicesSection } from './PluginServicesSection'
import type {
  AttachResult,
  EnablePreview,
  PluginCommand,
  PluginDependency,
  PluginDetails,
  PluginValidationResult,
} from '../../types/plugin'

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

// The plugins behind Nagios Core's own server checks (localhost.cfg). Pinpoint does
// not manage those services, so these are explained rather than offered for enabling.
const LOCAL_SERVER_PLUGINS = ['check_load', 'check_disk', 'check_swap', 'check_procs', 'check_users']

type Notice = { tone: 'ok' | 'error'; text: string }

// Say what the reconciler did after an enable or disable, from the route's auto_apply.
function describeAttach(action: 'enable' | 'disable', result: AttachResult | undefined): Notice | null {
  if (!result) return null
  if (!result.success) {
    return {
      tone: 'error',
      text: `Done, but Nagios was not updated: ${result.message}`,
    }
  }
  if (action === 'disable') {
    return {
      tone: 'ok',
      text: result.removed > 0
        ? `Stopped ${result.removed} service(s). Enabling again restores them.`
        : 'Disabled. No services were running.',
    }
  }
  return {
    tone: 'ok',
    text: result.applied > 0
      ? `Monitoring ${result.applied} new service(s) from discovered ports.`
      : 'Enabled. No matching services yet; they attach as devices are found.',
  }
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
  const { hasPermission } = useCurrentUser()
  const [updateFile, setUpdateFile] = useState<File | null>(null)
  const [updateUrl, setUpdateUrl] = useState('')
  const [updateResult, setUpdateResult] = useState<PluginUpdateResult | null>(null)
  const [rollbackNotice, setRollbackNotice] = useState<string | null>(null)
  const [preview, setPreview] = useState<EnablePreview | null>(null)
  const [attachNotice, setAttachNotice] = useState<Notice | null>(null)
  // Bumped after an enable or disable so the monitored-services list reloads.
  const [servicesKey, setServicesKey] = useState(0)

  async function load(showSpinner = true) {
    if (showSpinner) setIsLoading(true)
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
      await load(false)
      onChanged()
    } catch (err) {
      setActionError(errorMessage(err, 'Action failed.'))
    } finally {
      setIsBusy(false)
    }
  }

  // Enabling attaches every matching discovered port, so show what that is first.
  const handleEnable = async () => {
    setIsBusy(true)
    setActionError(null)
    setAttachNotice(null)
    try {
      setPreview(await getEnablePreview(pluginId))
    } catch (err) {
      setActionError(errorMessage(err, 'Unable to check what enabling would monitor.'))
    } finally {
      setIsBusy(false)
    }
  }

  const confirmEnable = () =>
    runAction(async () => {
      setPreview(null)
      const result = await enablePlugin(pluginId)
      setAttachNotice(describeAttach('enable', result.auto_apply))
      setServicesKey((key) => key + 1)
    })

  const handleDisable = () =>
    runAction(async () => {
      setAttachNotice(null)
      const result = await disablePlugin(pluginId)
      setAttachNotice(describeAttach('disable', result.auto_apply))
      setServicesKey((key) => key + 1)
    })

  const handleValidate = () =>
    runAction(async () => {
      setValidation(await validatePlugin(pluginId))
    })

  const handleUpdate = () =>
    runAction(async () => {
      setRollbackNotice(null)
      const result = await updatePlugin(
        pluginId,
        updateFile ? { file: updateFile } : { url: updateUrl.trim() }
      )
      setUpdateResult(result)
      setUpdateFile(null)
      setUpdateUrl('')
    })

  const handleRollback = () =>
    runAction(async () => {
      const result = await rollbackPluginUpdate(pluginId)
      setUpdateResult(null)
      setRollbackNotice(
        result.restored_version ? `Rolled back to version ${result.restored_version}.` : 'Update rolled back.'
      )
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

  const canEnable = details ? details.service_driven && !details.status.endsWith('Failed') && details.status !== 'Rollback' && details.status !== 'Active' && details.status !== 'Enabled' : false
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
                {details.documentation_url && (
                  <a
                    href={details.documentation_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-block text-xs font-medium text-[#b37b00] hover:underline dark:text-[#ffb100]"
                  >
                    Documentation
                  </a>
                )}

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
                    <dt className="text-gray-400">Category</dt>
                    <dd className="font-medium text-gray-900 dark:text-white">{details.category ?? '—'}</dd>
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

                <p className="mt-3 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-500 dark:bg-white/5 dark:text-gray-400">
                  Monitoring usage: {details.monitoring_usage.services} services /{' '}
                  {details.monitoring_usage.devices} devices.
                </p>

                {!details.service_driven && (
                  <p className="mt-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:border-white/10 dark:bg-white/5 dark:text-gray-300">
                    <span className="font-semibold">Not service-driven.</span>{' '}
                    {LOCAL_SERVER_PLUGINS.includes(details.name)
                      ? 'Checks the Nagios server itself through Nagios Core. Not managed here.'
                      : 'This plugin does not check a service that discovery finds on a port, so there is nothing to attach it to.'}
                  </p>
                )}

                {attachNotice && (
                  <p
                    role="status"
                    className={`mt-3 rounded-lg px-3 py-2 text-xs ${
                      attachNotice.tone === 'ok'
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300'
                        : 'bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300'
                    }`}
                  >
                    {attachNotice.text}
                  </p>
                )}

                <div className="mt-4 flex flex-wrap gap-2">
                  {details.service_driven && (
                    <button
                      type="button"
                      onClick={handleEnable}
                      disabled={isBusy || !canEnable}
                      className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Power className="h-4 w-4" /> Enable
                    </button>
                  )}
                  {(details.service_driven || canDisable) && (
                  <button
                    type="button"
                    onClick={handleDisable}
                    disabled={isBusy || !canDisable}
                    className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
                  >
                    <PowerOff className="h-4 w-4" /> Disable
                  </button>
                  )}
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

              {(hasPermission('plugin.update') || hasPermission('plugin.update_rollback')) && (
                <section>
                  <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">Update</h4>

                  {hasPermission('plugin.update') && (
                    <div className="space-y-2 rounded-xl border border-gray-200 p-3 dark:border-white/10">
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        Provide an update archive (.tar.gz, .tgz or .zip) or a URL to download one from. The update is
                        validated afterwards; a failed update can be rolled back.
                      </p>
                      <input
                        type="file"
                        accept=".tar.gz,.tgz,.zip"
                        aria-label="Update archive"
                        disabled={isBusy || !!updateUrl.trim()}
                        onChange={(e) => setUpdateFile(e.target.files?.[0] ?? null)}
                        className="block w-full text-xs text-gray-700 dark:text-gray-300"
                      />
                      <input
                        type="url"
                        placeholder="https://… (instead of a file)"
                        aria-label="Update URL"
                        value={updateUrl}
                        disabled={isBusy || !!updateFile}
                        onChange={(e) => setUpdateUrl(e.target.value)}
                        className="w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 outline-none focus:border-gray-500 dark:border-white/20 dark:bg-[#0D1117] dark:text-white"
                      />
                      <button
                        type="button"
                        onClick={handleUpdate}
                        disabled={isBusy || (!updateFile && !updateUrl.trim())}
                        className="rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Update plugin
                      </button>
                    </div>
                  )}

                  {updateResult && (
                    <div
                      className={`mt-3 space-y-1 rounded-lg px-3 py-2 text-sm ${
                        updateResult.success
                          ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300'
                          : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300'
                      }`}
                    >
                      {updateResult.success ? (
                        <p>
                          Updated{updateResult.previous_version ? ` from ${updateResult.previous_version}` : ''} to{' '}
                          {updateResult.current_version ?? 'the new version'}.
                        </p>
                      ) : (
                        <>
                          <p className="font-medium">
                            Update failed{updateResult.failed_step ? ` at ${updateResult.failed_step}` : ''}.
                          </p>
                          {updateResult.nagios_check && !updateResult.nagios_check.passed && (
                            <p className="font-mono text-xs">{updateResult.nagios_check.output}</p>
                          )}
                        </>
                      )}
                    </div>
                  )}

                  {rollbackNotice && (
                    <p className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300">
                      {rollbackNotice}
                    </p>
                  )}

                  {details.status === 'Rollback' && hasPermission('plugin.update_rollback') && (
                    <button
                      type="button"
                      onClick={handleRollback}
                      disabled={isBusy}
                      className="mt-3 flex items-center gap-2 rounded-lg border border-red-500/40 px-4 py-2 text-sm font-semibold text-red-600 hover:bg-red-500/10 disabled:opacity-50 dark:text-red-400"
                    >
                      <RotateCcw className="h-4 w-4" /> Roll back update
                    </button>
                  )}
                </section>
              )}

              {details.service_driven && (
                <PluginServicesSection
                  key={pluginId}
                  pluginId={pluginId}
                  refreshKey={servicesKey}
                  onChanged={async () => {
                    await load(false)
                    onChanged()
                  }}
                />
              )}

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

      {preview && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Enable ${preview.name}`}
          className="absolute inset-0 z-10 flex items-center justify-center bg-black/60 p-4"
        >
          <div className="w-full max-w-sm space-y-3 rounded-2xl bg-white p-5 shadow-xl dark:bg-[#171B20]">
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">Enable {preview.name}?</h3>
            <p className="text-sm text-gray-600 dark:text-gray-300">{preview.message}</p>
            {preview.held_ports > 0 && (
              <p className="text-xs text-gray-500 dark:text-gray-400">Monitor them from each device&apos;s Ports list.</p>
            )}
            {preview.matched_services > 0 && (
              <dl className="grid grid-cols-2 gap-2 text-sm">
                <div className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-white/5">
                  <dt className="text-xs text-gray-400">Services</dt>
                  <dd className="font-semibold text-gray-900 dark:text-white">{preview.matched_services}</dd>
                </div>
                <div className="rounded-lg bg-gray-50 px-3 py-2 dark:bg-white/5">
                  <dt className="text-xs text-gray-400">Devices</dt>
                  <dd className="font-semibold text-gray-900 dark:text-white">{preview.matched_devices}</dd>
                </div>
              </dl>
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Devices are not picked by hand. New devices that run this service are added automatically, and you can
              stop monitoring any one of them afterwards.
            </p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPreview(null)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmEnable}
                disabled={isBusy}
                className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:opacity-50"
              >
                Confirm enable
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
