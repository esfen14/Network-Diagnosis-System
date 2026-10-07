import { useCallback, useEffect, useState } from 'react'
import { Loader2, Pause, Play, Search } from 'lucide-react'
import { errorMessage } from '../../lib/api'
import {
  getPluginServices,
  resumeServiceMonitoring,
  stopServiceMonitoring,
} from '../../lib/pluginApi'
import { useCurrentUser } from '../../contexts/CurrentUserContext'
import type { PluginServiceItem, ServiceStatusKind } from '../../types/plugin'
import { useDisplayTime } from '../../hooks/useDisplayTime'

type Props = {
  pluginId: number
  // Bumped by the drawer after the plugin is enabled or disabled so the list reloads.
  refreshKey: number
  onChanged: () => void | Promise<void>
}

const PER_PAGE = 5

const STATUS_STYLES: Record<ServiceStatusKind, string> = {
  ok: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  warning: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  critical: 'bg-red-500/15 text-red-600 dark:text-red-400',
  unknown: 'bg-gray-500/15 text-gray-600 dark:text-gray-300',
  waiting: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  stale: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  stopped: 'bg-gray-400/15 text-gray-500 dark:text-gray-400',
  paused: 'bg-gray-400/15 text-gray-500 dark:text-gray-400',
}

const STATUS_LABELS: Record<ServiceStatusKind, string> = {
  ok: 'OK',
  warning: 'Warning',
  critical: 'Critical',
  unknown: 'Unknown',
  waiting: 'Waiting',
  stale: 'No recent data',
  stopped: 'Stopped',
  paused: 'Paused',
}

// A port is identified by its device, protocol and number; a service name alone is not unique.
function rowKey(item: PluginServiceItem) {
  return `${item.device.id}-${item.protocol}-${item.port}-${item.service}`
}

export function PluginServicesSection({ pluginId, refreshKey, onChanged }: Props) {
  const { formatDateTime } = useDisplayTime()
  const { hasPermission } = useCurrentUser()
  const canStop = hasPermission('plugin.disable')
  const canResume = hasPermission('plugin.enable')

  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [page, setPage] = useState(1)
  const [items, setItems] = useState<PluginServiceItem[]>([])
  const [meta, setMeta] = useState({ pages: 1, total: 0, hasNext: false, hasPrev: false })
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    const timeout = setTimeout(() => {
      setDebouncedQuery(query)
      setPage(1)
    }, 350)
    return () => clearTimeout(timeout)
  }, [query])

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const data = await getPluginServices(pluginId, { page, per_page: PER_PAGE, search: debouncedQuery })
      setItems(data.items)
      setMeta({ pages: data.pages, total: data.total, hasNext: data.has_next, hasPrev: data.has_prev })
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load the monitored services.'))
    } finally {
      setIsLoading(false)
    }
  }, [pluginId, page, debouncedQuery])

  useEffect(() => {
    void load()
  }, [load, refreshKey])

  const change = async (item: PluginServiceItem, resume: boolean) => {
    const ref = { device_id: item.device.id, protocol: item.protocol, port: item.port }
    setBusyKey(rowKey(item))
    setActionError(null)
    try {
      if (resume) await resumeServiceMonitoring(pluginId, ref)
      else await stopServiceMonitoring(pluginId, ref)
      await load()
      await onChanged()
    } catch (err) {
      setActionError(errorMessage(err, resume ? 'Unable to resume monitoring.' : 'Unable to stop monitoring.'))
    } finally {
      setBusyKey(null)
    }
  }

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Monitored services</h4>
        <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1 dark:border-white/10 dark:bg-[#0D1117]">
          <Search className="h-3.5 w-3.5 text-gray-500" />
          <input
            type="search"
            aria-label="Search monitored services"
            placeholder="Search service, device or IP"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-44 bg-transparent text-xs text-gray-900 outline-none placeholder:text-gray-500 dark:text-white"
          />
        </div>
      </div>

      {loadError && (
        <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-300">
          {loadError}
        </p>
      )}
      {actionError && (
        <p role="alert" className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-300">
          {actionError}
        </p>
      )}

      {isLoading ? (
        <div className="flex items-center py-6 text-sm text-gray-500 dark:text-gray-400">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading services…
        </div>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-gray-300 px-3 py-4 text-sm text-gray-500 dark:border-white/15 dark:text-gray-400">
          {debouncedQuery
            ? 'No monitored services match your search.'
            : 'No services yet. Enabled plugins attach the ports that Network Discovery finds, including devices found later.'}
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => {
            const key = rowKey(item)
            const busy = busyKey === key
            const allowed = item.monitored ? canStop : canResume
            return (
              <div key={key} className="rounded-xl border border-gray-200 p-3 dark:border-white/10">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="break-all font-mono text-sm font-medium text-gray-900 dark:text-white">{item.service}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {item.device.hostname} · {item.device.ip_address}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[item.status.kind]}`}
                  >
                    {STATUS_LABELS[item.status.kind]}
                  </span>
                </div>

                <p className="mt-1.5 break-words text-xs text-gray-600 dark:text-gray-300">{item.status.output}</p>

                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span>
                    {item.monitored ? `Running since ${formatDateTime(item.running_since)}` : 'Not monitored'}
                  </span>
                  {allowed && (
                    <button
                      type="button"
                      onClick={() => change(item, !item.monitored)}
                      disabled={busy}
                      aria-label={`${item.monitored ? 'Stop monitoring' : 'Resume monitoring'} ${item.service} on ${item.device.hostname}`}
                      className="flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
                    >
                      {busy ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : item.monitored ? (
                        <Pause className="h-3 w-3" />
                      ) : (
                        <Play className="h-3 w-3" />
                      )}
                      {item.monitored ? 'Stop monitoring' : 'Resume'}
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>
          Page {page} of {meta.pages} · {meta.total} {meta.total === 1 ? 'service' : 'services'}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setPage(page - 1)}
            disabled={!meta.hasPrev}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10"
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setPage(page + 1)}
            disabled={!meta.hasNext}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10"
          >
            Next
          </button>
        </div>
      </div>
    </section>
  )
}
