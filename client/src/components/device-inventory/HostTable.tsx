import { ArrowUpDown, Filter, Search } from 'lucide-react'
import type { Host, HostState } from '../../types/host'

type HostTableProps = {
  hosts: Host[]
  title: string
  isLoading: boolean
  query: string
  onQueryChange: (query: string) => void
  stateFilter: 'All' | HostState
  onStateFilterChange: (state: 'All' | HostState) => void
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
  onAcknowledge: (host: Host) => void
  onUnacknowledge: (host: Host) => void
}

function StateBadge({ state }: { state: HostState }) {
  const styles: Record<HostState, string> = {
    UP: 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    DOWN: 'bg-red-500/20 text-red-600 dark:text-red-400',
    UNREACHABLE: 'bg-amber-500/20 text-amber-600 dark:text-amber-400',
  }
  const dots: Record<HostState, string> = {
    UP: 'bg-emerald-500 dark:bg-emerald-400',
    DOWN: 'bg-red-500 dark:bg-red-400',
    UNREACHABLE: 'bg-amber-500 dark:bg-amber-400',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[state]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dots[state]}`} />
      {state}
    </span>
  )
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function HostTable({
  hosts,
  title,
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
}: HostTableProps) {
  const states: ('All' | HostState)[] = ['All', 'UP', 'DOWN', 'UNREACHABLE']

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">
      <div className="relative flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {title}
        </h2>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
            <Search className="h-4 w-4 text-gray-500" />
            <input
              type="search"
              placeholder="Search hostname"
              value={query}
              onChange={(e) => onQueryChange(e.target.value)}
              className="w-32 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-500 dark:text-white"
            />
          </div>

          <div className="relative">
            <button
              type="button"
              onClick={onToggleFilter}
              aria-label="Filter"
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
            aria-label="Sort"
            title={sortAsc ? 'Sorted A → Z' : 'Sorted Z → A'}
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-225 text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-500">
              <th className="px-4 py-3 font-normal">Hostname</th>
              <th className="px-4 py-3 font-normal">State</th>
              <th className="px-4 py-3 font-normal">Latency</th>
              <th className="px-4 py-3 font-normal">Last Check</th>
              <th className="px-4 py-3 font-normal">Flags</th>
              <th className="px-4 py-3 font-normal">Acknowledgement</th>
              <th className="px-4 py-3 font-normal">Actions</th>
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  Loading hosts…
                </td>
              </tr>
            ) : hosts.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  No hosts match your search or filter
                </td>
              </tr>
            ) : (
              hosts.map((host) => (
                <tr
                  key={host.hostname}
                  className="border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
                >
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{host.hostname}</td>
                  <td className="px-4 py-3"><StateBadge state={host.state} /></td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{host.checkLatency.toFixed(3)}s</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{formatDateTime(host.lastCheck)}</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    {[host.isFlapping && 'Flapping', host.inDowntime && 'Downtime'].filter(Boolean).join(', ') || '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    {host.ack ? (
                      <span title={host.ack.comment}>By {host.ack.acknowledgedBy}</span>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {host.state !== 'UP' && !host.ack && (
                      <button
                        type="button"
                        onClick={() => onAcknowledge(host)}
                        className="rounded-lg bg-[#ffb100] px-3 py-1 text-xs font-semibold text-black hover:brightness-105"
                      >
                        Acknowledge
                      </button>
                    )}
                    {host.ack && (
                      <button
                        type="button"
                        onClick={() => onUnacknowledge(host)}
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
        <span>
          Page {page} of {pageCount} · {total} hosts total
        </span>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onPageChange(page - 1)}
            disabled={!hasPrev}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10"
          >
            Previous
          </button>

          <span className="rounded-lg bg-white border border-gray-200 px-3 py-1 text-gray-900 shadow-sm dark:bg-white/10 dark:text-white dark:border-transparent">
            {page}
          </span>

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
