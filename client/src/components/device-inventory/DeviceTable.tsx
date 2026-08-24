import { useState, useMemo } from 'react'
import { ArrowUpDown, Filter, Search } from 'lucide-react'
import type { Device } from '../../data/devices'

type DeviceTableProps = {
  devices: Device[]
  title: string
}

function StatusBadge({ status }: { status: Device['status'] }) {
  const isOnline = status === 'Online'

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
        isOnline
          ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400'
          : 'bg-red-500/20 text-red-600 dark:text-red-400'
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          isOnline
            ? 'bg-emerald-500 dark:bg-emerald-400'
            : 'bg-red-500 dark:bg-red-400'
        }`}
      />
      {status}
    </span>
  )
}

export function DeviceTable({
  devices,
  title,
}: DeviceTableProps) {
  const [query, setQuery] = useState('')
  const [sortAsc, setSortAsc] = useState(true)
  const [showFilter, setShowFilter] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'All' | Device['status']>('All')

  const statuses = useMemo(
    () => ['All', ...Array.from(new Set(devices.map((d) => d.status)))] as const,
    [devices]
  )

  const filtered = useMemo(() => {
    let result = devices

    if (statusFilter !== 'All') {
      result = result.filter((d) => d.status === statusFilter)
    }

    if (query.trim()) {
      const q = query.toLowerCase()
      result = result.filter(
        (d) =>
          d.id.toLowerCase().includes(q) ||
          d.hostName.toLowerCase().includes(q) ||
          d.deviceType.toLowerCase().includes(q) ||
          d.deviceIp.toLowerCase().includes(q) ||
          d.osVersion.toLowerCase().includes(q) ||
          d.router.toLowerCase().includes(q)
      )
    }

    result = [...result].sort((a, b) =>
      sortAsc ? a.id.localeCompare(b.id) : b.id.localeCompare(a.id)
    )

    return result
  }, [devices, query, statusFilter, sortAsc])

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
              placeholder="Search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-32 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-500 dark:text-white"
            />
          </div>

          {/* Filter */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowFilter((v) => !v)}
              aria-label="Filter"
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
            aria-label="Sort"
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
              <th className="px-4 py-3 font-normal">
                Device ID
              </th>

              <th className="px-4 py-3 font-normal">
                Host Name
              </th>

              <th className="px-4 py-3 font-normal">
                Device Type
              </th>

              <th className="px-4 py-3 font-normal">
                Device IP
              </th>

              <th className="px-4 py-3 font-normal">
                OS Version
              </th>

              <th className="px-4 py-3 font-normal">
                Router
              </th>

              <th className="px-4 py-3 font-normal">
                Status
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
                  No devices match your search or filter
                </td>
              </tr>
            ) : (
              filtered.map((device) => (
                <tr
                  key={device.id}
                  className="border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
                >
                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.id}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.hostName}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.deviceType}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.deviceIp}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.osVersion}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {device.router}
                  </td>

                  <td className="px-4 py-3">
                    <StatusBadge status={device.status} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>
          Showing {filtered.length} of {devices.length} devices
        </span>

        <div className="flex gap-2">
          <button
            type="button"
            disabled
            className="rounded-lg px-3 py-1 hover:bg-gray-100 dark:hover:bg-white/10"
          >
            Previous
          </button>

          <button
            type="button"
            className="rounded-lg bg-gray-100 px-3 py-1 text-gray-900 dark:bg-white/10 dark:text-white"
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