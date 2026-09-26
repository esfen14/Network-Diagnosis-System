import { useEffect, useState } from 'react'
import { Activity, Search } from 'lucide-react'
import { errorMessage } from '../../lib/api'
import { getRunningChecks } from '../../lib/pluginApi'
import type { RunningCheck } from '../../types/plugin'

const PER_PAGE = 10

type Props = {
  // Bumped by the page whenever plugins change, so the list reloads.
  refreshKey: number
  onSelectPlugin: (pluginId: number) => void
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// "Currently Running" tab: every plugin applied to a device and running as
// a live Nagios check. A plugin applied to several devices has one row per
// device. Clicking a row opens that plugin's details.
export function RunningChecksTable({ refreshKey, onSelectPlugin }: Props) {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [page, setPage] = useState(1)

  const [checks, setChecks] = useState<RunningCheck[]>([])
  const [meta, setMeta] = useState({ pages: 1, total: 0, hasNext: false, hasPrev: false })
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    const timeout = setTimeout(() => {
      setDebouncedQuery(query)
      setPage(1)
    }, 350)
    return () => clearTimeout(timeout)
  }, [query])

  useEffect(() => {
    let cancelled = false

    getRunningChecks({ page, per_page: PER_PAGE, search: debouncedQuery })
      .then((data) => {
        if (cancelled) return
        setChecks(data.items)
        setMeta({ pages: Math.max(1, data.pages), total: data.total, hasNext: data.has_next, hasPrev: data.has_prev })
        setLoadError(null)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(errorMessage(err, 'Unable to load running checks.'))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [page, debouncedQuery, refreshKey])

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Currently Running</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Plugins applied to a device and running as live Nagios checks.
          </p>
        </div>

        <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
          <Search className="h-4 w-4 text-gray-500" />
          <input
            type="search"
            placeholder="Search checks"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-40 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-500 dark:text-white"
          />
        </div>
      </div>

      {loadError && (
        <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
          {loadError}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-225 text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-500">
              <th className="px-4 py-3 font-normal">Plugin</th>
              <th className="px-4 py-3 font-normal">Device</th>
              <th className="px-4 py-3 font-normal">IP Address</th>
              <th className="px-4 py-3 font-normal">Service</th>
              <th className="px-4 py-3 font-normal">Running Since</th>
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  Loading running checks…
                </td>
              </tr>
            ) : checks.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                  <Activity className="mx-auto mb-2 h-5 w-5 opacity-60" />
                  {debouncedQuery
                    ? 'No running checks match your search'
                    : 'No plugins are running yet. Apply a plugin to a device from its details to start monitoring.'}
                </td>
              </tr>
            ) : (
              checks.map((check) => (
                <tr
                  key={check.id}
                  onClick={() => onSelectPlugin(check.plugin.id)}
                  className="cursor-pointer border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
                >
                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    <span className="inline-flex items-center gap-2">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400" />
                      {check.plugin.display_name || check.plugin.name}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                    {check.target?.hostname || '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                    {check.target?.ip_address ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                    {check.service_description || '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    {formatDateTime(check.applied_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>
          Page {page} of {meta.pages} · {meta.total} running {meta.total === 1 ? 'check' : 'checks'}
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

          <span className="rounded-lg bg-white border border-gray-200 px-3 py-1 text-gray-900 shadow-sm dark:bg-white/10 dark:text-white dark:border-transparent">
            {page}
          </span>

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
    </div>
  )
}
