import { useMemo, useState } from 'react'
import { ArrowUpDown, Search } from 'lucide-react'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'
import { exportRows } from '../../utils/exportData'
import { ExportMenu } from '../shared/ExportMenu'
import type { ServiceRow } from '../../types/report'

type NetworkServicesReportTableProps = {
  services: ServiceRow[]
  isLoading: boolean
  title?: string
}

const PAGE_SIZE = 10

export function NetworkServicesReportTable({
  services,
  isLoading,
  title = 'Network Services Report',
}: NetworkServicesReportTableProps) {
  const { settings } = useSystemSettings()
  const [query, setQuery] = useState('')
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(1)

  const filtered = useMemo(() => {
    let result = services
    if (query.trim()) {
      const q = query.toLowerCase()
      result = result.filter((s) => s.service.toLowerCase().includes(q))
    }
    return [...result].sort((a, b) =>
      sortAsc ? a.service.localeCompare(b.service) : b.service.localeCompare(a.service)
    )
  }, [services, query, sortAsc])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const paginated = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  const exportData = filtered.map((s) => ({
    Service: s.service,
    'Total Instances': s.totalInstances,
    OK: s.ok,
    Warning: s.warning,
    Critical: s.critical,
    Unknown: s.unknown,
    'Uptime %': s.uptimePct ?? '',
  }))

  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">
      <div className="relative flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
            <Search className="h-4 w-4 text-gray-500" />
            <input
              placeholder="Search service"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setPage(1) }}
              className="bg-transparent text-sm text-gray-800 outline-none placeholder:text-gray-500 dark:text-white"
            />
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
            onExport={(format) => exportRows(exportData, format, 'network-services-report')}
          />
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-275 text-left text-sm">
          <thead className="border-b border-gray-200 text-gray-500 dark:border-white/10 dark:text-gray-500">
            <tr>
              <th className="px-4 py-3">Service</th>
              <th className="px-4 py-3">Instances</th>
              <th className="px-4 py-3">OK</th>
              <th className="px-4 py-3">Warning</th>
              <th className="px-4 py-3">Critical</th>
              <th className="px-4 py-3">Unknown</th>
              <th className="px-4 py-3">Uptime %</th>
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">Loading…</td></tr>
            ) : paginated.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  {query ? 'No services match your search' : 'No data in this period'}
                </td>
              </tr>
            ) : (
              paginated.map((svc) => (
                <tr key={svc.service} className="border-b border-gray-100 hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5">
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{svc.service}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{svc.totalInstances}</td>
                  <td className="px-4 py-3 text-emerald-600 dark:text-emerald-400">{svc.ok}</td>
                  <td className="px-4 py-3 text-amber-600 dark:text-amber-400">{svc.warning}</td>
                  <td className="px-4 py-3 text-red-600 dark:text-red-400">{svc.critical}</td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{svc.unknown}</td>
                  <td className="px-4 py-3 text-gray-900 dark:text-white">{svc.uptimePct ?? '—'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>Showing {filtered.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length} services</span>
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
