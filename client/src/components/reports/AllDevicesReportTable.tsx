import { useState, useMemo } from 'react'
import {
  ArrowUpDown,
  Download,
  Filter,
  Search,
} from 'lucide-react'

function StatusBadge({
  status,
}: {
  status: 'Up' | 'Down'
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
        status === 'Up'
          ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400'
          : 'bg-red-500/20 text-red-600 dark:text-red-400'
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          status === 'Up'
            ? 'bg-emerald-500 dark:bg-emerald-400'
            : 'bg-red-500 dark:bg-red-400'
        }`}
      />
      {status}
    </span>
  )
}

export function AllDevicesReportTable() {
  type Device = {
    id: number
    deviceId: string
    temperature: number
    cpu: number
    memory: number
    status: 'Up' | 'Down'
    uptime: string
    timestamp: string
  }

  const devices = useMemo<Device[]>(() => [], [])

  const [query, setQuery] = useState('')
  const [sortAsc, setSortAsc] = useState(true)
  const [showFilter, setShowFilter] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'All' | 'Up' | 'Down'>('All')

  const filtered = useMemo(() => {
    let result = devices

    if (statusFilter !== 'All') {
      result = result.filter((d) => d.status === statusFilter)
    }

    if (query.trim()) {
      const q = query.toLowerCase()
      result = result.filter(
        (d) =>
          d.deviceId.toLowerCase().includes(q) ||
          d.status.toLowerCase().includes(q) ||
          d.timestamp.toLowerCase().includes(q)
      )
    }

    result = [...result].sort((a, b) =>
      sortAsc
        ? a.deviceId.localeCompare(b.deviceId)
        : b.deviceId.localeCompare(a.deviceId)
    )

    return result
  }, [devices, query, statusFilter, sortAsc])

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">

      <div className="relative flex items-center justify-between border-b border-gray-200 p-4 dark:border-white/10">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          All Devices Report
        </h2>

        <div className="flex gap-2">

          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
            <Search className="h-4 w-4 text-gray-500" />

            <input
              placeholder="Search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="bg-transparent text-sm text-gray-800 outline-none placeholder:text-gray-500 dark:text-white"
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
                  : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10'
              }`}
            >
              <Filter className="h-4 w-4" />
            </button>

            {showFilter && (
              <div className="absolute right-0 top-full z-10 mt-2 w-40 rounded-xl border border-gray-200 bg-white p-2 shadow-lg dark:border-white/10 dark:bg-[#171B20]">
                <span className="block px-2 py-1 text-xs font-medium text-gray-400">
                  Status
                </span>
                {(['All', 'Up', 'Down'] as const).map((s) => (
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
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>

          <button
            type="button"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
          >
            <Download className="h-4 w-4" />
          </button>

        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-275 text-left text-sm">

          <thead className="border-b border-gray-200 text-gray-500 dark:border-white/10 dark:text-gray-500">
            <tr>
              <th className="px-4 py-3">
                Device ID
              </th>

              <th className="px-4 py-3">
                Temperature (°C)
              </th>

              <th className="px-4 py-3">
                CPU Utilization (%)
              </th>

              <th className="px-4 py-3">
                Memory Utilization (%)
              </th>

              <th className="px-4 py-3">
                Status
              </th>

              <th className="px-4 py-3">
                Uptime (%)
              </th>

              <th className="px-4 py-3">
                Timestamp
              </th>
            </tr>
          </thead>

          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-8 text-center text-gray-500 dark:text-gray-400"
                >
                  {query || statusFilter !== 'All' ? 'No devices match your search or filter' : 'No devices to show'}
                </td>
              </tr>
            ) : (
              filtered.map((device) => (
                <tr
                  key={device.id}
                  className="border-b border-gray-100 hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
                >
                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.deviceId}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.temperature}°C
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.cpu}%
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.memory}%
                  </td>

                  <td className="px-4 py-3">
                    <StatusBadge status={device.status} />
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.uptime}%
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.timestamp}
                  </td>
                </tr>
              ))
            )}
          </tbody>

        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>
          Showing {filtered.length} of {devices.length} records
        </span>

        <div className="flex gap-2">

          <button
            type="button"
            disabled
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed dark:hover:bg-white/10"
          >
            Previous
          </button>

          <button
            type="button"
            className="rounded-lg bg-white border border-gray-200 px-3 py-1 text-gray-900 shadow-sm hover:bg-gray-50 dark:bg-white/10 dark:text-white dark:border-transparent dark:hover:bg-white/20"
          >
            1
          </button>

          <button
            type="button"
            className="rounded-lg px-3 py-1 hover:bg-gray-100 dark:hover:bg-white/10"
          >
            Next
          </button>

        </div>
      </div>

    </div>
  )
}