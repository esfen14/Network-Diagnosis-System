import { ArrowUpDown, Filter, Search } from 'lucide-react'
import type { ServiceRow, ServiceState } from '../../types/service'

type ServiceStatusTableProps = {
  services: ServiceRow[]
  title?: string
  isLoading: boolean
  query: string
  onQueryChange: (query: string) => void
  stateFilter: 'All' | ServiceState
  onStateFilterChange: (state: 'All' | ServiceState) => void
  showFilter: boolean
  onToggleFilter: () => void
  sortAsc: boolean
  onToggleSort: () => void
  page: number
  pageCount: number
  total: number
  hasNext: boolean
  hasPrev: boolean
  onPageChange: (page: number) => void
  onAcknowledge: (service: ServiceRow) => void
  onUnacknowledge: (service: ServiceRow) => void
}

function StatusPill({ status }: { status: ServiceState }) {
  const styles: Record<ServiceState, string> = {
    OK: 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    WARNING: 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400',
    CRITICAL: 'bg-red-500/20 text-red-600 dark:text-red-400',
    UNKNOWN: 'bg-orange-500/20 text-orange-600 dark:text-orange-400',
  }
  const dotStyles: Record<ServiceState, string> = {
    OK: 'bg-emerald-500 dark:bg-emerald-400',
    WARNING: 'bg-yellow-500 dark:bg-yellow-400',
    CRITICAL: 'bg-red-500 dark:bg-red-400',
    UNKNOWN: 'bg-orange-500 dark:bg-orange-400',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotStyles[status]}`} />
      {status}
    </span>
  )
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function ServiceStatusTable({
  services,
  title = 'Service Status Details For All Hosts',
  isLoading,
  query,
  onQueryChange,
  stateFilter,
  onStateFilterChange,
  showFilter,
  onToggleFilter,
  sortAsc,
  onToggleSort,
  page,
  pageCount,
  total,
  hasNext,
  hasPrev,
  onPageChange,
  onAcknowledge,
  onUnacknowledge,
}: ServiceStatusTableProps) {
  const states: ('All' | ServiceState)[] = ['All', 'OK', 'WARNING', 'CRITICAL', 'UNKNOWN']

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">

      <div className="relative flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {title}
        </h2>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
            <Search className="h-4 w-4 text-gray-500" />
            <input
              type="search"
              placeholder="Search host or service"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              className="w-48 bg-transparent text-sm text-gray-900 placeholder:text-gray-500 outline-none dark:text-white"
            />
          </div>

          <div className="relative">
            <button
              type="button"
              onClick={onToggleFilter}
              className={`rounded-lg p-2 ${
                showFilter || stateFilter !== 'All'
                  ? 'bg-gray-200 text-gray-900 dark:bg-white/20 dark:text-white'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white'
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
                    onClick={() => onStateFilterChange(s)}
                    className={`block w-full rounded-lg px-2 py-1.5 text-left text-sm ${
                      stateFilter === s
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
            onClick={onToggleSort}
            title={sortAsc ? 'Sorted A → Z' : 'Sorted Z → A'}
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[950px] text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-500">
              <th className="px-4 py-3 font-normal">Host</th>
              <th className="px-4 py-3 font-normal">Service</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Last Check</th>
              <th className="px-4 py-3 font-normal">Acknowledgement</th>
              <th className="px-4 py-3 font-normal">Actions</th>
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  Loading services…
                </td>
              </tr>
            ) : services.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  No services match your search or filter
                </td>
              </tr>
            ) : (
              services.map((s) => (
                <tr
                  key={`${s.hostname}-${s.service}`}
                  className="border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
                >
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{s.hostname}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{s.service}</td>
                  <td className="px-4 py-3"><StatusPill status={s.state} /></td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{formatDateTime(s.lastCheck)}</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    {s.ack ? <span title={s.ack.comment}>By {s.ack.acknowledgedBy}</span> : '—'}
                  </td>
                  <td className="px-4 py-3">
                    {s.state !== 'OK' && !s.ack && (
                      <button
                        type="button"
                        onClick={() => onAcknowledge(s)}
                        className="rounded-lg bg-[#ffb100] px-3 py-1 text-xs font-semibold text-black hover:brightness-105"
                      >
                        Acknowledge
                      </button>
                    )}
                    {s.ack && (
                      <button
                        type="button"
                        onClick={() => onUnacknowledge(s)}
                        className="rounded-lg border border-gray-300 px-3 py-1 text-xs text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
                      >
                        Unacknowledge
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>Page {page} of {pageCount} · {total} services total</span>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={!hasPrev}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10"
          >
            Previous
          </button>
          <span className="rounded-lg bg-gray-900 px-3 py-1 text-white dark:bg-white/10">{page}</span>
          <button
            type="button"
            onClick={() => onPageChange(page + 1)}
            disabled={!hasNext}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10"
          >
            Next
          </button>
        </div>
      </div>

    </div>
  )
}
