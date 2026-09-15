import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { PageHeader } from '../components/shared/PageHeader'
import { useSystemSettings } from '../contexts/SystemSettingsContext'
import { formatDateTime } from '../utils/formatDateTime'
import { exportRows } from '../utils/exportData'
import { ExportMenu } from '../components/shared/ExportMenu'
import { apiGet, errorMessage } from '../lib/api'
import { LOG_ENDPOINTS, type LogCategory, type LogEntry, type LogListResponse } from '../types/log'

const PER_PAGE = 10

export function SystemLogsPage() {
  const { settings } = useSystemSettings()
  const [activeTab, setActiveTab] = useState<LogCategory>('activity')
  const [selectedLog, setSelectedLog] = useState<LogEntry | null>(null)

  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [page, setPage] = useState(1)

  const [items, setItems] = useState<LogEntry[]>([])
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
    setPage(1)
    setSelectedLog(null)
  }, [activeTab, startDate, endDate])

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setLoadError(null)
      try {
        const params = new URLSearchParams({
          page: String(page),
          per_page: String(PER_PAGE),
        })
        if (debouncedQuery) params.set('search', debouncedQuery)
        if (startDate) params.set('start_date', startDate)
        if (endDate) params.set('end_date', endDate)

        const data = await apiGet<LogListResponse>(`${LOG_ENDPOINTS[activeTab]}?${params.toString()}`)
        if (cancelled) return
        setItems(data.items)
        setMeta({ pages: data.pages, total: data.total, hasNext: data.has_next, hasPrev: data.has_prev })
      } catch (err) {
        if (cancelled) return
        setLoadError(errorMessage(err, 'Unable to load logs.'))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [activeTab, page, debouncedQuery, startDate, endDate])

  const getTabLabel = (tab: LogCategory) => {
    switch (tab) {
      case 'activity':
        return 'Activity Log'
      case 'configurationChange':
        return 'Configuration Change'
      case 'networkDiscovery':
        return 'Network Discovery'
      case 'ncpaDeployment':
        return 'NCPA Deployment'
      case 'exportLog':
        return 'Export Log'
    }
  }

  return (
    <main className="ml-[220px] flex-1">
      <div className="space-y-6">

        <PageHeader title="System Logs" description="Monitor events and system activities." />

        {loadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
            {loadError}
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-6 border-b border-[var(--border)]">
          {(['activity', 'configurationChange', 'networkDiscovery', 'ncpaDeployment', 'exportLog'] as LogCategory[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 text-sm transition ${
                activeTab === tab
                  ? 'border-b-2 border-[var(--text)] font-medium text-[var(--text)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text)]'
              }`}
            >
              {getTabLabel(tab)}
            </button>
          ))}
        </div>

        {/* Search + date range filter */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2">
            <Search className="h-4 w-4 text-[var(--text-muted)]" />
            <input
              type="search"
              placeholder="Search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-40 bg-transparent text-sm text-[var(--text)] outline-none placeholder:text-[var(--text-muted)]"
            />
          </div>

          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="h-10 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--text)] outline-none transition duration-200 focus:border-[#ffb100]"
          />
          <span className="text-sm text-[var(--text-muted)]">to</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="h-10 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--text)] outline-none transition duration-200 focus:border-[#ffb100]"
          />
          {(startDate || endDate || query) && (
            <button
              type="button"
              onClick={() => {
                setStartDate('')
                setEndDate('')
                setQuery('')
              }}
              className="text-sm text-[var(--text-muted)] hover:text-[var(--text)]"
            >
              Clear
            </button>
          )}
        </div>

        <div className="flex gap-6">
          {/* Log list */}
          <div className="flex-1 space-y-4">
            <div className="grid grid-cols-[1fr_180px_120px] px-4 text-sm text-[var(--text-muted)]">
              <span>Activity</span><span>Timestamp</span><span>Tag ID</span>
            </div>
            <div className="space-y-2">
              {isLoading ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] px-4 py-8 text-center text-sm text-[var(--text-muted)]">
                  Loading logs…
                </div>
              ) : items.length === 0 ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] px-4 py-8 text-center text-sm text-[var(--text-muted)]">
                  No logs match your search or filter
                </div>
              ) : (
                items.map((log) => (
                  <div
                    key={log.id}
                    onClick={() => setSelectedLog(log)}
                    className={`grid grid-cols-[1fr_180px_120px] items-center px-4 py-3 rounded-xl cursor-pointer border transition ${
                      selectedLog?.id === log.id
                        ? 'border-[var(--border)] bg-[var(--hover)]'
                        : 'border-[var(--border)] bg-[var(--card)] hover:bg-[var(--hover)]'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-6 h-6 flex items-center justify-center rounded font-bold text-xs ${
                        log.type === 'account' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300'
                        : log.type === 'network' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300'
                        : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                      }`}>!</div>
                      <span className="text-sm text-[var(--text)]">
                        <strong>{log.title}</strong>{' '}
                        <span className="text-[var(--text-muted)]">{log.description}</span>
                      </span>
                    </div>
                    <span className="text-[var(--text-muted)] text-sm">
                      {formatDateTime(new Date(log.timestamp), settings.dateTimeFormat, settings.timeZone)}
                    </span>
                    <span className="text-[var(--text-muted)] text-sm">{log.tagId}</span>
                  </div>
                ))
              )}
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between px-4 text-sm text-[var(--text-muted)]">
              <span>Page {page} of {meta.pages} · {meta.total} logs total</span>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={!meta.hasPrev}
                  className="rounded-lg px-3 py-1 hover:bg-[var(--hover)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Previous
                </button>
                <button
                  type="button"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!meta.hasNext}
                  className="rounded-lg px-3 py-1 hover:bg-[var(--hover)] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          </div>

          {/* Detail panel */}
          <div className="w-[300px] bg-[var(--card)] border border-[var(--border)] rounded-2xl p-4 space-y-4">
            {selectedLog ? (
              <>
                <h3 className="text-sm font-semibold border-b border-[var(--border)] pb-2 text-[var(--text)]">{selectedLog.title}</h3>
                <p className="text-sm text-[var(--text-muted)]">{selectedLog.description}</p>
                <div className="text-xs text-[var(--text-muted)] space-y-1">
                  <p>Tag ID: {selectedLog.tagId}</p>
                  <p>User: {selectedLog.user}</p>
                  <p>Date &amp; Time: {formatDateTime(new Date(selectedLog.timestamp), settings.dateTimeFormat, settings.timeZone)}</p>
                  {selectedLog.details && Object.entries(selectedLog.details).map(([key, value]) => (
                    value == null || value === '' ? null : (
                      <p key={key} className="capitalize">
                        {key.replace(/_/g, ' ')}: {String(value)}
                      </p>
                    )
                  ))}
                </div>
                <div className="flex gap-2 pt-4">
                  <button onClick={() => setSelectedLog(null)} className="flex-1 bg-[var(--text)] text-[var(--card)] py-2 rounded-lg text-sm">Close</button>
                  <ExportMenu
                    allowedFormats={settings.exportFormats}
                    className="flex-1"
                    buttonClassName="w-full bg-[var(--hover)] border border-[var(--border)] py-2 rounded-lg text-sm text-[var(--text)] hover:bg-[var(--card-alt)]"
                    onExport={(format) =>
                      exportRows([selectedLog], format, `log-${selectedLog.tagId}`)
                    }
                  />
                </div>

              </>
            ) : (
              <div className="text-[var(--text-muted)] text-sm">Select a log to view details</div>
            )}
          </div>
        </div>

      </div>
    </main>
  )
}
