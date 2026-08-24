import { useState, useMemo } from 'react'
import {
  ArrowUpDown,
  Download,
  Filter,
  Search,
} from 'lucide-react'
import type { Report } from '../../data/reports'

type LinkHealthReportTableProps = {
  reports: Report[]
  title?: string
}

export function LinkHealthReportTable({
  reports,
  title = 'Link Health Report',
}: LinkHealthReportTableProps) {
  const [query, setQuery] = useState('')
  const [sortAsc, setSortAsc] = useState(true)
  const [showFilter, setShowFilter] = useState(false)
  const [linkTypeFilter, setLinkTypeFilter] = useState<string>('All')

  const linkTypes = useMemo(
    () => ['All', ...Array.from(new Set(reports.map((r) => r.linkType)))],
    [reports]
  )

  const filtered = useMemo(() => {
    let result = reports

    if (linkTypeFilter !== 'All') {
      result = result.filter((r) => r.linkType === linkTypeFilter)
    }

    if (query.trim()) {
      const q = query.toLowerCase()
      result = result.filter(
        (r) =>
          r.linkId.toLowerCase().includes(q) ||
          r.localInterface.toLowerCase().includes(q) ||
          r.remoteInterface.toLowerCase().includes(q) ||
          r.remoteDevice.toLowerCase().includes(q) ||
          r.linkType.toLowerCase().includes(q) ||
          r.discoveryMethod.toLowerCase().includes(q)
      )
    }

    result = [...result].sort((a, b) =>
      sortAsc
        ? a.linkId.localeCompare(b.linkId)
        : b.linkId.localeCompare(a.linkId)
    )

    return result
  }, [reports, query, linkTypeFilter, sortAsc])

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
              className="w-36 bg-transparent text-sm text-gray-800 placeholder:text-gray-500 outline-none dark:text-white dark:placeholder:text-gray-500"
            />
          </div>

          {/* Filter */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowFilter((v) => !v)}
              className={`rounded-lg p-2 ${
                showFilter || linkTypeFilter !== 'All'
                  ? 'bg-gray-200 text-gray-900 dark:bg-white/20 dark:text-white'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white'
              }`}
            >
              <Filter className="h-4 w-4" />
            </button>

            {showFilter && (
              <div className="absolute right-0 top-full z-10 mt-2 w-48 rounded-xl border border-gray-200 bg-white p-2 shadow-lg dark:border-white/10 dark:bg-[#171B20]">
                <span className="block px-2 py-1 text-xs font-medium text-gray-400">
                  Link Type
                </span>
                {linkTypes.map((t) => (
                  <button
                    key={t}
                    onClick={() => {
                      setLinkTypeFilter(t)
                      setShowFilter(false)
                    }}
                    className={`block w-full rounded-lg px-2 py-1.5 text-left text-sm ${
                      linkTypeFilter === t
                        ? 'bg-[#ffb100]/20 text-[#ffb100]'
                        : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/10'
                    }`}
                  >
                    {t}
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

          <button
            type="button"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <Download className="h-4 w-4" />
          </button>

        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1200px] text-left text-sm">

          <thead>
            <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-500">
              <th className="px-4 py-3 font-normal">
                Link ID
              </th>

              <th className="px-4 py-3 font-normal">
                Local Interface
              </th>

              <th className="px-4 py-3 font-normal">
                Remote Interface
              </th>

              <th className="px-4 py-3 font-normal">
                Remote Device
              </th>

              <th className="px-4 py-3 font-normal">
                Link Speed
              </th>

              <th className="px-4 py-3 font-normal">
                Link Type
              </th>

              <th className="px-4 py-3 font-normal">
                Discovery Method
              </th>

              <th className="px-4 py-3 font-normal">
                Duplex
              </th>

              <th className="px-4 py-3 font-normal">
                Timestamp
              </th>
            </tr>
          </thead>

          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td
                  colSpan={9}
                  className="px-4 py-8 text-center text-gray-500 dark:text-gray-400"
                >
                  No links match your search or filter
                </td>
              </tr>
            ) : (
              filtered.map((report) => (
                <tr
                  key={report.id}
                  className="border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
                >
                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {report.linkId}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {report.localInterface}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {report.remoteInterface}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {report.remoteDevice}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {report.linkSpeed}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {report.linkType}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {report.discoveryMethod}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {report.duplex}
                  </td>

                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {report.timestamp}
                  </td>
                </tr>
              ))
            )}
          </tbody>

        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">

        <span>
          Showing {filtered.length} of {reports.length} records
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
            className="rounded-lg bg-gray-900 px-3 py-1 text-white dark:bg-white/10"
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