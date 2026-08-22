import { useMemo, useState } from 'react'
import { ArrowUpDown, Filter, Search } from 'lucide-react'

export type ServiceStatus = 'OK' | 'Warning' | 'Unknown' | 'Critical' | 'Pending'

export type ServiceRow = {
  id: number
  host: string
  service: string
  status: ServiceStatus
  lastCheck: string
  duration: string
}

type Props = {
  services: ServiceRow[]
  title?: string
}

function StatusPill({ status }: { status: ServiceStatus }) {
  const styles: Record<ServiceStatus, string> = {
    OK: 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    Warning: 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400',
    Unknown: 'bg-orange-500/20 text-orange-600 dark:text-orange-400',
    Critical: 'bg-red-500/20 text-red-600 dark:text-red-400',
    Pending: 'bg-gray-500/20 text-gray-500 dark:text-gray-400',
  }

  const dotStyles: Record<ServiceStatus, string> = {
    OK: 'bg-emerald-500 dark:bg-emerald-400',
    Warning: 'bg-yellow-500 dark:bg-yellow-400',
    Unknown: 'bg-orange-500 dark:bg-orange-400',
    Critical: 'bg-red-500 dark:bg-red-400',
    Pending: 'bg-gray-400',
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotStyles[status]}`} />
      {status}
    </span>
  )
}

export function ServiceStatusTable({
  services,
  title = 'Service Status Details For All Hosts',
}: Props) {
  const [query, setQuery] = useState('')
  const [sortAsc, setSortAsc] = useState(true)
  const [showFilter, setShowFilter] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'All' | ServiceStatus>('All')

  const statuses: ('All' | ServiceStatus)[] = ['All', 'OK', 'Warning', 'Unknown', 'Critical', 'Pending']

  const filtered = useMemo(() => {
    let result = services

    if (statusFilter !== 'All') {
      result = result.filter((s) => s.status === statusFilter)
    }

    if (query.trim()) {
      const q = query.toLowerCase()
      result = result.filter(
        (s) =>
          s.host.toLowerCase().includes(q) ||
          s.service.toLowerCase().includes(q) ||
          s.status.toLowerCase().includes(q)
      )
    }

    result = [...result].sort((a, b) =>
      sortAsc ? a.host.localeCompare(b.host) : b.host.localeCompare(a.host)
    )

    return result
  }, [services, query, statusFilter, sortAsc])

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
              placeholder="Search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-40 bg-transparent text-sm text-gray-900 placeholder:text-gray-500 outline-none dark:text-white"
            />
          </div>

          {/* Filter */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowFilter((v) => !v)}
              className={`rounded-lg p-2 ${
                showFilter || statusFilter !== 'All'
                  ? 'bg-gray-200 text-gray-900 dark:bg-white/20 dark:text-white'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white'
              }`}
            >
              <Filter className="h-4 w-4" />
            </button>

            {showFilter && (
              <div className="absolute right-0 top-full z-10 mt-2 w-40 rounded-xl border border-gray-200 bg-white p-2 shadow-lg dark:border-white/10 dark:bg-[#171B20]">
                <span className="block px-2 py-1 text-xs font-medium text-gray-400">
                  Status
                </span>
                {statuses.map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setStatusFilter(s)
                      setShowFilter(false)
                    }}
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

          {/* Sort */}
          <button
            type="button"
            onClick={() => setSortAsc((v) => !v)}
            title={sortAsc ? 'Sorted A → Z' : 'Sorted Z → A'}
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-500">
              <th className="px-4 py-3 font-normal">Host</th>
              <th className="px-4 py-3 font-normal">Service</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Last Check</th>
              <th className="px-4 py-3 font-normal">Duration</th>
            </tr>
          </thead>

          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  No services match your search or filter
                </td>
              </tr>
            ) : (
              filtered.map((s) => (
                <tr
                  key={s.id}
                  className="border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
                >
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{s.host}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{s.service}</td>
                  <td className="px-4 py-3"><StatusPill status={s.status} /></td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{s.lastCheck}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{s.duration}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>Showing {filtered.length} of {services.length} services</span>

        <div className="flex gap-2">
          <button type="button" disabled className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed dark:hover:bg-white/10">
            Previous
          </button>
          <button type="button" className="rounded-lg bg-gray-900 px-3 py-1 text-white dark:bg-white/10">
            1
          </button>
          <button type="button" className="rounded-lg px-3 py-1 hover:bg-gray-100 dark:hover:bg-white/10">
            Next
          </button>
        </div>
      </div>

    </div>
  )
}