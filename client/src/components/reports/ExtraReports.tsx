import { useEffect, useMemo, useState } from 'react'
import { Activity, ArrowUpDown, Bell, CheckCircle2, Filter, Search, Server, XCircle } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { useSystemSettings } from '../../contexts/SystemSettingsContext'
import { apiGet, errorMessage } from '../../lib/api'
import { formatDateTime } from '../../utils/formatDateTime'
import { exportRows } from '../../utils/exportData'
import { ExportMenu } from '../shared/ExportMenu'


export type ExtraReportView = 'hosts-by-os' | 'device-services' | 'alerts' | 'notifications'

type Props = {
  view: ExtraReportView
  query: string
  runKey: number
  onStatus: (message: { type: 'success' | 'error'; text: string } | null) => void
  onCards: (cards: ExtraReportCard[]) => void
}

type ColumnKind = 'text' | 'state' | 'datetime' | 'pct'

type Column = { key: string; label: string; kind: ColumnKind }

type Row = Record<string, string | number | null>

export type ExtraReportCard = { title: string; value: string; subtitle: string; icon: LucideIcon; gradient: string }

type Report = {
  title: string
  noun: string
  filename: string
  searchLabel: string
  searchKeys: string[]
  filterKey: string | null
  filterLabel: string
  sortKey: string
  columns: Column[]
  rows: Row[]
  cards: ExtraReportCard[]
}

type NagiosEvent = Record<string, unknown>

const PAGE_SIZE = 10

const GOLD = 'linear-gradient(135deg,#FFB100,#F59E0B)'
const GREEN = 'linear-gradient(135deg,#22C55E,#16A34A)'
const RED = 'linear-gradient(135deg,#EF4444,#DC2626)'
const GRAY = 'linear-gradient(135deg,#6B7280,#4B5563)'

function nagiosList(raw: unknown): NagiosEvent[] {
  if (Array.isArray(raw)) return raw as NagiosEvent[]
  if (raw && typeof raw === 'object') return Object.values(raw as Record<string, NagiosEvent>)
  return []
}

function text(value: unknown) {
  return value == null || value === '' ? '' : String(value)
}

function eventTime(value: unknown) {
  const ts = Number(value)
  return ts ? new Date(ts * 1000).toISOString() : null
}

function isGood(state: string) {
  return ['UP', 'OK', 'RECOVERY'].includes(state.toUpperCase())
}

function buildReport(view: ExtraReportView, data: Record<string, unknown>): Report {
  if (view === 'hosts-by-os') {
    const byOs = data.by_os as {
      os_type: string
      hosts: { hostname: string; state: string; uptime_pct: number | null; last_check: string | null; last_state_change: string | null }[]
    }[]
    const rows: Row[] = []
    for (const group of byOs) {
      for (const host of group.hosts) {
        rows.push({
          os: group.os_type,
          hostname: host.hostname,
          state: host.state,
          uptime: host.uptime_pct,
          lastCheck: host.last_check,
          lastStateChange: host.last_state_change,
        })
      }
    }
    return {
      title: 'Hosts by OS Report',
      noun: 'hosts',
      filename: 'hosts-by-os-report',
      searchLabel: 'Search hostname or OS',
      searchKeys: ['hostname', 'os'],
      filterKey: 'state',
      filterLabel: 'State',
      sortKey: 'hostname',
      columns: [
        { key: 'os', label: 'OS', kind: 'text' },
        { key: 'hostname', label: 'Hostname', kind: 'text' },
        { key: 'state', label: 'State', kind: 'state' },
        { key: 'uptime', label: 'Uptime %', kind: 'pct' },
        { key: 'lastCheck', label: 'Last Check', kind: 'datetime' },
        { key: 'lastStateChange', label: 'Last State Change', kind: 'datetime' },
      ],
      rows,
      cards: [],
    }
  }

  if (view === 'device-services') {
    const hosts = data.hosts as {
      hostname: string
      uptime_pct: number | null
      services: {
        service: string; state: string; uptime_pct: number | null; total_snapshots: number
        last_check: string | null; last_state_change: string | null; plugin_output: string
      }[]
    }[]
    const rows: Row[] = []
    for (const host of hosts) {
      for (const svc of host.services) {
        rows.push({
          hostname: host.hostname,
          service: svc.service,
          state: svc.state,
          uptime: svc.uptime_pct,
          snapshots: svc.total_snapshots,
          lastCheck: svc.last_check,
          lastStateChange: svc.last_state_change,
        })
      }
    }
    return {
      title: 'Device Services Report',
      noun: 'services',
      filename: 'device-services-report',
      searchLabel: 'Search host or service',
      searchKeys: ['hostname', 'service'],
      filterKey: 'state',
      filterLabel: 'State',
      sortKey: 'hostname',
      columns: [
        { key: 'hostname', label: 'Hostname', kind: 'text' },
        { key: 'service', label: 'Service', kind: 'text' },
        { key: 'state', label: 'State', kind: 'state' },
        { key: 'uptime', label: 'Uptime %', kind: 'pct' },
        { key: 'snapshots', label: 'Snapshots', kind: 'text' },
        { key: 'lastCheck', label: 'Last Check', kind: 'datetime' },
        { key: 'lastStateChange', label: 'Last State Change', kind: 'datetime' },
      ],
      rows,
      cards: [],
    }
  }

  if (view === 'alerts') {
    const rows: Row[] = nagiosList(data.alerts).map((a) => ({
      time: eventTime(a.timestamp),
      hostname: text(a.hostname),
      service: text(a.service_description),
      previousState: text(a.last_state).toUpperCase(),
      state: text(a.state).toUpperCase(),
      output: text(a.plugin_output),
    }))
    const problems = rows.filter((r) => !isGood(String(r.state))).length
    const hostsAffected = new Set(rows.map((r) => r.hostname)).size
    return {
      title: 'Alerts Report',
      noun: 'alerts',
      filename: 'alerts-report',
      searchLabel: 'Search host or service',
      searchKeys: ['hostname', 'service', 'output'],
      filterKey: 'state',
      filterLabel: 'New state',
      sortKey: 'time',
      columns: [
        { key: 'time', label: 'Time', kind: 'datetime' },
        { key: 'hostname', label: 'Hostname', kind: 'text' },
        { key: 'service', label: 'Service', kind: 'text' },
        { key: 'previousState', label: 'Previous State', kind: 'state' },
        { key: 'state', label: 'New State', kind: 'state' },
        { key: 'output', label: 'Output', kind: 'text' },
      ],
      rows,
      cards: [
        { title: 'Total Alerts', value: String(rows.length), subtitle: 'State changes in this period', icon: Bell, gradient: GOLD },
        { title: 'Recoveries', value: String(rows.length - problems), subtitle: 'Returned to OK / UP', icon: CheckCircle2, gradient: GREEN },
        { title: 'Problems', value: String(problems), subtitle: 'Warning / critical / down', icon: XCircle, gradient: RED },
        { title: 'Hosts Affected', value: String(hostsAffected), subtitle: 'With at least one alert', icon: Server, gradient: GRAY },
      ],
    }
  }

  const rows: Row[] = nagiosList(data.notifications).map((n) => ({
    time: eventTime(n.timestamp),
    hostname: text(n.hostname),
    service: text(n.service_description),
    state: text(n.notification_reason ?? n.state).toUpperCase(),
    contact: text(n.contact),
    message: text(n.output),
  }))
  const recoveries = rows.filter((r) => isGood(String(r.state))).length
  const contacts = new Set(rows.map((r) => r.contact).filter(Boolean)).size
  return {
    title: 'Notifications Report',
    noun: 'notifications',
    filename: 'notifications-report',
    searchLabel: 'Search host, service or contact',
    searchKeys: ['hostname', 'service', 'contact'],
    filterKey: 'state',
    filterLabel: 'State',
    sortKey: 'time',
    columns: [
      { key: 'time', label: 'Time', kind: 'datetime' },
      { key: 'hostname', label: 'Hostname', kind: 'text' },
      { key: 'service', label: 'Service', kind: 'text' },
      { key: 'state', label: 'State', kind: 'state' },
      { key: 'contact', label: 'Contact', kind: 'text' },
      { key: 'message', label: 'Message', kind: 'text' },
    ],
    rows,
    cards: [
      { title: 'Total Notifications', value: String(rows.length), subtitle: 'Sent in this period', icon: Bell, gradient: GOLD },
      { title: 'Recoveries', value: String(recoveries), subtitle: 'Recovery notices', icon: CheckCircle2, gradient: GREEN },
      { title: 'Problems', value: String(rows.length - recoveries), subtitle: 'Needs attention', icon: XCircle, gradient: RED },
      { title: 'Contacts', value: String(contacts), subtitle: 'Notified', icon: Activity, gradient: GRAY },
    ],
  }
}

function StateBadge({ state }: { state: string }) {
  if (!state) return <span className="text-gray-500 dark:text-gray-400">—</span>
  const good = isGood(state)
  const warn = state.toUpperCase() === 'WARNING' || state.toUpperCase() === 'UNKNOWN'
  const tone = good
    ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400'
    : warn
      ? 'bg-amber-500/20 text-amber-600 dark:text-amber-400'
      : 'bg-red-500/20 text-red-600 dark:text-red-400'
  const dot = good ? 'bg-emerald-500 dark:bg-emerald-400' : warn ? 'bg-amber-500 dark:bg-amber-400' : 'bg-red-500 dark:bg-red-400'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${tone}`}>
      <span className={`h-2 w-2 rounded-full ${dot}`} />
      {state}
    </span>
  )
}

export function ExtraReports({ view, query, runKey, onStatus, onCards }: Props) {
  const { settings } = useSystemSettings()
  const [report, setReport] = useState<Report | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showFilter, setShowFilter] = useState(false)
  const [stateFilter, setStateFilter] = useState('All')
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(1)

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setReport(null)
    onCards([])
    setSearch('')
    setStateFilter('All')
    setPage(1)
    apiGet<Record<string, unknown>>(`/api/system/report/${view}?${query}`)
      .then((data) => {
        if (cancelled) return
        const built = buildReport(view, data)
        setSortAsc(built.sortKey !== 'time')
        setReport(built)
        onCards(built.cards)
        onStatus(null)
      })
      .catch((err) => {
        if (!cancelled) onStatus({ type: 'error', text: errorMessage(err, 'Could not run report. Please try again.') })
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, runKey])

  const states = useMemo(() => {
    if (!report?.filterKey) return ['All']
    return ['All', ...Array.from(new Set(report.rows.map((r) => String(r[report.filterKey!] ?? '')).filter(Boolean)))]
  }, [report])

  const filtered = useMemo(() => {
    if (!report) return []
    let result = report.rows
    if (report.filterKey && stateFilter !== 'All') {
      result = result.filter((r) => String(r[report.filterKey!]) === stateFilter)
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter((r) => report.searchKeys.some((k) => String(r[k] ?? '').toLowerCase().includes(q)))
    }
    return [...result].sort((a, b) => {
      const av = a[report.sortKey] ?? ''
      const bv = b[report.sortKey] ?? ''
      const cmp = String(av).localeCompare(String(bv))
      return sortAsc ? cmp : -cmp
    })
  }, [report, search, stateFilter, sortAsc])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const paginated = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  function exportData() {
    if (!report) return []
    return filtered.map((row) => {
      const out: Record<string, string | number> = {}
      for (const col of report.columns) out[col.label] = row[col.key] ?? ''
      return out
    })
  }

  function renderCell(col: Column, row: Row) {
    const value = row[col.key]
    if (col.kind === 'state') return <StateBadge state={String(value ?? '')} />
    if (col.kind === 'datetime') {
      return value ? formatDateTime(new Date(String(value)), settings.dateTimeFormat, settings.timeZone) : '—'
    }
    if (col.kind === 'pct') return value == null ? '—' : value
    return value === '' || value == null ? '—' : value
  }

  const columnCount = report?.columns.length ?? 1

  return (
    <>
      <div className="rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">
        <div className="relative flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{report?.title ?? 'Report'}</h2>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
              <Search className="h-4 w-4 text-gray-500" />
              <input
                placeholder={report?.searchLabel ?? 'Search'}
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1) }}
                className="bg-transparent text-sm text-gray-800 outline-none placeholder:text-gray-500 dark:text-white"
              />
            </div>

            {report?.filterKey && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setShowFilter((v) => !v)}
                  className={`rounded-lg p-2 ${
                    showFilter || stateFilter !== 'All'
                      ? 'bg-gray-200 text-gray-900 dark:bg-white/20 dark:text-white'
                      : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10'
                  }`}
                >
                  <Filter className="h-4 w-4" />
                </button>

                {showFilter && (
                  <div className="absolute right-0 top-full z-10 mt-2 w-40 rounded-xl border border-gray-200 bg-white p-2 shadow-lg dark:border-white/10 dark:bg-[#171B20]">
                    <span className="block px-2 py-1 text-xs font-medium text-gray-400">{report.filterLabel}</span>
                    {states.map((s) => (
                      <button
                        key={s}
                        onClick={() => { setStateFilter(s); setShowFilter(false); setPage(1) }}
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
            )}

            <button
              type="button"
              onClick={() => setSortAsc((v) => !v)}
              title={sortAsc ? 'Sorted ascending' : 'Sorted descending'}
              className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/10"
            >
              <ArrowUpDown className="h-4 w-4" />
            </button>

            <ExportMenu
              allowedFormats={settings.exportFormats}
              onExport={(format) => report && exportRows(exportData(), format, report.filename)}
            />
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-275 text-left text-sm">
            <thead className="border-b border-gray-200 text-gray-500 dark:border-white/10 dark:text-gray-500">
              <tr>
                {(report?.columns ?? []).map((col) => (
                  <th key={col.key} className="px-4 py-3">{col.label}</th>
                ))}
              </tr>
            </thead>

            <tbody>
              {isLoading ? (
                <tr><td colSpan={columnCount} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">Loading…</td></tr>
              ) : paginated.length === 0 ? (
                <tr>
                  <td colSpan={columnCount} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                    {search || stateFilter !== 'All' ? `No ${report?.noun} match your search or filter` : 'No data in this period'}
                  </td>
                </tr>
              ) : (
                paginated.map((row, i) => (
                  <tr key={i} className="border-b border-gray-100 hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5">
                    {report!.columns.map((col) => (
                      <td key={col.key} className="max-w-xs truncate px-4 py-3 text-gray-900 dark:text-white">
                        {renderCell(col, row)}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
          <span>
            Showing {filtered.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length} {report?.noun ?? 'rows'}
          </span>
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
    </>
  )
}
