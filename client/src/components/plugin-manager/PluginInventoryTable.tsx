import { ArrowUpDown, Filter, RefreshCw, Search } from 'lucide-react'
import type { PluginListItem, PluginStatus, PluginType } from '../../types/plugin'

type Props = {
  plugins: PluginListItem[]
  isLoading: boolean
  query: string
  onQueryChange: (query: string) => void
  typeFilter: 'All' | PluginType
  onTypeFilterChange: (type: 'All' | PluginType) => void
  statusFilter: 'All' | PluginStatus | 'Failed'
  onStatusFilterChange: (status: 'All' | PluginStatus | 'Failed') => void
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
  onSelectPlugin: (plugin: PluginListItem) => void
  onScan: () => void
  isScanning: boolean
}

const STATUS_OPTIONS: ('All' | PluginStatus | 'Failed')[] = [
  'All',
  'Ready',
  'Enabled',
  'Active',
  'Disabled',
  'Update Available',
  'Failed',
  'Rollback',
]

const TYPE_OPTIONS: ('All' | PluginType)[] = ['All', 'Nagios', 'Custom']

function StatusBadge({ status }: { status: PluginStatus }) {
  const isFailed = status.endsWith('Failed')
  const styles: Record<string, string> = {
    Active: 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400',
    Enabled: 'bg-blue-500/20 text-blue-600 dark:text-blue-400',
    Ready: 'bg-gray-500/20 text-gray-600 dark:text-gray-300',
    Installed: 'bg-gray-500/20 text-gray-600 dark:text-gray-300',
    Available: 'bg-amber-500/20 text-amber-600 dark:text-amber-400',
    Disabled: 'bg-gray-400/20 text-gray-500 dark:text-gray-400',
    'Update Available': 'bg-amber-500/20 text-amber-600 dark:text-amber-400',
    Rollback: 'bg-orange-500/20 text-orange-600 dark:text-orange-400',
  }
  const dots: Record<string, string> = {
    Active: 'bg-emerald-500 dark:bg-emerald-400',
    Enabled: 'bg-blue-500 dark:bg-blue-400',
    Ready: 'bg-gray-500 dark:bg-gray-300',
    Installed: 'bg-gray-500 dark:bg-gray-300',
    Available: 'bg-amber-500 dark:bg-amber-400',
    Disabled: 'bg-gray-400 dark:bg-gray-500',
    'Update Available': 'bg-amber-500 dark:bg-amber-400',
    Rollback: 'bg-orange-500 dark:bg-orange-400',
  }
  const style = isFailed
    ? 'bg-red-500/20 text-red-600 dark:text-red-400'
    : styles[status] ?? 'bg-gray-500/20 text-gray-600 dark:text-gray-300'
  const dot = isFailed ? 'bg-red-500 dark:bg-red-400' : dots[status] ?? 'bg-gray-500'

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
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

export function PluginInventoryTable({
  plugins,
  isLoading,
  query,
  onQueryChange,
  typeFilter,
  onTypeFilterChange,
  statusFilter,
  onStatusFilterChange,
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
  onSelectPlugin,
  onScan,
  isScanning,
}: Props) {
  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">
      <div className="relative flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          Plugin Inventory
        </h2>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
            <Search className="h-4 w-4 text-gray-500" />
            <input
              type="search"
              placeholder="Search plugins"
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
                showFilter || typeFilter !== 'All' || statusFilter !== 'All'
                  ? 'bg-gray-200 text-gray-900 dark:bg-white/20 dark:text-white'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white'
              }`}
            >
              <Filter className="h-4 w-4" />
            </button>

            {showFilter && (
              <div className="absolute right-0 top-full z-10 mt-2 w-48 rounded-xl border border-gray-200 bg-white p-2 shadow-lg dark:border-white/10 dark:bg-[#171B20]">
                <span className="block px-2 py-1 text-xs font-medium text-gray-400">Type</span>
                {TYPE_OPTIONS.map((t) => (
                  <button
                    key={t}
                    onClick={() => onTypeFilterChange(t)}
                    className={`block w-full rounded-lg px-2 py-1.5 text-left text-sm ${
                      typeFilter === t
                        ? 'bg-[#ffb100]/20 text-[#ffb100]'
                        : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/10'
                    }`}
                  >
                    {t}
                  </button>
                ))}

                <span className="mt-2 block border-t border-gray-100 px-2 py-1 pt-2 text-xs font-medium text-gray-400 dark:border-white/10">
                  Status
                </span>
                {STATUS_OPTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => onStatusFilterChange(s)}
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
            onClick={onToggleSort}
            aria-label="Sort"
            title={sortAsc ? 'Sorted A → Z' : 'Sorted Z → A'}
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={onScan}
            disabled={isScanning}
            className="flex items-center gap-2 rounded-lg bg-[#ffb100] px-3 py-2 text-sm font-semibold text-black hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${isScanning ? 'animate-spin' : ''}`} />
            {isScanning ? 'Scanning…' : 'Scan for Plugins'}
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-225 text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-500">
              <th className="px-4 py-3 font-normal">Plugin</th>
              <th className="px-4 py-3 font-normal">Type</th>
              <th className="px-4 py-3 font-normal">Source</th>
              <th className="px-4 py-3 font-normal">Version</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Updated</th>
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  Loading plugins…
                </td>
              </tr>
            ) : plugins.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                  No plugins match your search or filter
                </td>
              </tr>
            ) : (
              plugins.map((plugin) => (
                <tr
                  key={plugin.id}
                  onClick={() => onSelectPlugin(plugin)}
                  className="cursor-pointer border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
                >
                  <td className="px-4 py-3 text-gray-900 dark:text-white">
                    {plugin.display_name || plugin.name}
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{plugin.type}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{plugin.source}</td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                    {plugin.current_version ?? '—'}
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={plugin.status} /></td>
                  <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                    {formatDateTime(plugin.updated_at)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>
          Page {page} of {pageCount} · {total} plugins total
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
