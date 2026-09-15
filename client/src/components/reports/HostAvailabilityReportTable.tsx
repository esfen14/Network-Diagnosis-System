import { useMemo, useState } from 'react'
import { ArrowUpDown, Filter, Search } from 'lucide-react'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'
import { formatDateTime } from '../../utils/formatDateTime'
import { exportRows } from '../../utils/exportData'
import { ExportMenu } from '../shared/ExportMenu'
import type { HostAvailabilityRow } from '../../types/report'

type HostAvailabilityReportTableProps = {
  hosts: HostAvailabilityRow[]
  isLoading: boolean
  title?: string
}

const PAGE_SIZE = 10

function StatusBadge({ state }: { state: string }) {
  const isUp = state === 'Up'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
        isUp
          ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400'
          : 'bg-red-500/20 text-red-600 dark:text-red-400'
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${isUp ? 'bg-emerald-500 dark:bg-emerald-400' : 'bg-red-500 dark:bg-red-400'}`} />
      {state}
    </span>
  )
}

export function HostAvailabilityReportTable({
  hosts,
  isLoading,
  title = 'Host Availability Report',
}: HostAvailabilityReportTableProps) {
  const { settings } = useSystemSettings()
  const [query, setQuery] = useState('')
  const [sortAsc, setSortAsc] = useState(true)
  const [showFilter, setShowFilter] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('All')
  const [page, setPage] = useState(1)

  const states = useMemo(() => ['All', ...Array.from(new Set(hosts.map((h) => h.state)))], [hosts])

  const filtered = useMemo(() => {
    let result = hosts

    if (statusFilter !== 'All') {
      result = result.filter((h) => h.state === statusFilter)
    }

    if (query.trim()) {
      const q = query.toLowerCase()
      result = result.filter((h) => h.hostname.toLowerCase().includes(q))
    }

    return [...result].sort((a, b) =>
      sortAsc ? a.hostname.localeCompare(b.hostname) : b.hostname.localeCompare(a.hostname)
    )
  }, [hosts, query, statusFilter, sortAsc])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const paginated = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  const exportData = filtered.map((h) => ({
    Hostname: h.hostname,
    State: h.state,
    'Uptime %': h.uptimePct ?? '',
    'Total Snapshots': h.totalSnapshots,
    'Last Check': h.lastCheck ?? '',
    'Last State Change': h.lastStateChange ?? '',
  }))

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">
      <div className="relative flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
            <Search className="h-4 w-4 text-gray-500" />
            <input
              placeholder="Search hostname"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setPage(1) }}
              className="bg-transparent text-sm text-gray-800 outline-none placeholder:text-gray-500 dark:text-white"
            />
          </div>

          <div className="relative">
            <button
              type="button"
              onClick={() => setShowFilter((v) => !v)}
              className={`rounded-lg p-2 ${
                showFilter || statusFilter !== 'All'
                  ? 'bg-gray-200 text-gray-900 dark:bg-white/20 dark:text-white'
                  : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10'
              }`}
            >
              <Filter className="h-4 w-4" />
            </button>

            {showFilter && (
              <div className="absolute right-0 top-full z-10 mt-2 w-40 rounded-xl border border-gray-200 bg-white p-2 shadow-lg dark:border-white/10 dark:bg-[#171B20]">
                <span className="block px-2 py-1 text-xs font-medium text-gray-400">State</span>
                {states.map((s) => (
                  <button
                    key={s}
                    onClick={() => { setStatusFilter(s); setShowFilter(false); setPage(1) }}
                    className={`block w-full rounded-lg px-2 py-1.5 text-left text-sm ${
                      statusFilter === s
                        ? 'bg-[#ffb100]/20 text-[#ffb100]'
                        : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/10'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={() => setSortAsc((v) => !v)}
            title={sortAsc ? 'Sorted A → Z' : 'Sorted Z → A'}
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>

          <ExportMenu
            allowedFormats={settings.exportFormats}
            onExport={(format) => exportRows(exportData, format, 'host-availability-report')}
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-275 text-left text-sm">
          <thead className="border-b border-gray-200 text-gray-500 dark:border-white/10 dark:text-gray-500">
            <tr>
              <th className="px-4 py-3">Hostname</th>
              <th className="px-4 py-3">State</th>
              <th className="px-4 py-3">Uptime %</th>
              <th className="px-4 py-3">Snapshots</th>
              <th className="px-4 py-3">Last Check</th>
              <th className="px-4 py-3">Last State Change</th>
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">Loading…</td></tr>
            ) : paginated.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  {query || statusFilter !== 'All' ? 'No hosts match your search or filter' : 'No data in this period'}
                </td>
              </tr>
            ) : (
              paginated.map((host) => (
                <tr key={host.hostname} className="border-b border-gray-100 hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5">
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{host.hostname}</td>
                  <td className="px-4 py-3"><StatusBadge state={host.state} /></td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{host.uptimePct ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{host.totalSnapshots}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {host.lastCheck ? formatDateTime(new Date(host.lastCheck), settings.dateTimeFormat, settings.timeZone) : '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {host.lastStateChange ? formatDateTime(new Date(host.lastStateChange), settings.dateTimeFormat, settings.timeZone) : '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>Showing {filtered.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length} hosts</span>
        <div className="flex gap-2">
          <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={currentPage <= 1}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10">
            Previous
          </button>
          <span className="rounded-lg bg-white border border-gray-200 px-3 py-1 text-gray-900 shadow-sm dark:bg-white/10 dark:text-white dark:border-transparent">
            {currentPage} / {pageCount}
          </span>
          <button type="button" onClick={() => setPage((p) => Math.min(pageCount, p + 1))} disabled={currentPage >= pageCount}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10">
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
