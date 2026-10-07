import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Loader2, RefreshCw } from 'lucide-react'

import { PageHeader } from '../components/shared/PageHeader'
import { apiGet, errorMessage } from '../lib/api'
import { formatTimeAgo } from '../utils/formatDateTime'


type HistoryTab = 'alerts' | 'notifications'

type Page<T> = {
  items: T[]
  page: number
  per_page: number
  total: number
  pages: number
}

type AlertEvent = {
  timestamp: number
  type: 'host' | 'service'
  hostname: string
  service_name: string | null
  previous_state: string
  new_state: string
  state_type: string
  duration_seconds: number
  plugin_output: string
  acknowledged: boolean
}

type AlertDetail = AlertEvent & {
  ack: { acknowledged_by: string | null; acknowledged_at: string; comment: string | null } | null
  recovery_duration: number | null
  linked_notifications: { timestamp: number; contact: string; state: string; message: string }[]
}

type NotificationEvent = {
  source: 'nagios' | 'pinpoint'
  id?: number
  timestamp: number
  type: 'host' | 'service' | 'scan'
  hostname: string
  service_name: string | null
  state: string
  contact: string
  method: string
  message: string
}

type NotificationDetail = NotificationEvent & {
  contacts: string[]
  linked_alert: { timestamp: number; new_state: string; prev_state: string } | null
}

type Filters = {
  preset: string
  startDate: string
  endDate: string
  type: string
  hostname: string
  service: string
  state: string
  stateType: string
  ack: string
  contact: string
  source: string
}

const EMPTY_FILTERS: Filters = {
  preset: '24h',
  startDate: '',
  endDate: '',
  type: '',
  hostname: '',
  service: '',
  state: '',
  stateType: '',
  ack: 'all',
  contact: '',
  source: '',
}

const PRESETS = [
  { value: '1h', label: 'Last hour' },
  { value: '6h', label: 'Last 6 hours' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'custom', label: 'Custom range' },
]

const STATE_OPTIONS = ['OK', 'UP', 'WARNING', 'CRITICAL', 'DOWN', 'UNKNOWN', 'UNREACHABLE']
const PINPOINT_STATE_OPTIONS = ['SUCCESS', 'FAILED', 'CANCELLED']

const CONTROL_CLASS =
  'h-10 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--text)] outline-none transition duration-200 focus:border-[#ffb100]'

function stateBadgeClass(state: string) {
  switch (state) {
    case 'OK':
    case 'UP':
    case 'RECOVERY':
    case 'SUCCESS':
      return 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
    case 'WARNING':
      return 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
    case 'CRITICAL':
    case 'DOWN':
    case 'FAILED':
      return 'bg-red-500/15 text-red-600 dark:text-red-400'
    default:
      return 'bg-gray-500/15 text-[var(--text-muted)]'
  }
}

function StateBadge({ state }: { state: string }) {
  if (!state) return <span className="text-[var(--text-faint)]">—</span>
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${stateBadgeClass(state)}`}>
      {state}
    </span>
  )
}

function SourceBadge({ source }: { source: 'nagios' | 'pinpoint' }) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
        source === 'pinpoint'
          ? 'bg-[#ffb100]/20 text-[#b37a00] dark:text-[#ffb100]'
          : 'bg-sky-500/15 text-sky-700 dark:text-sky-300'
      }`}
    >
      {source === 'pinpoint' ? 'Pinpoint' : 'Nagios'}
    </span>
  )
}

function formatDuration(seconds: number) {
  if (!seconds || seconds < 1) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const parts: string[] = []
  if (d) parts.push(`${d}d`)
  if (h) parts.push(`${h}h`)
  if (m) parts.push(`${m}m`)
  if (!d && !h && s) parts.push(`${s}s`)
  return parts.join(' ') || '—'
}

function absoluteTime(ts: number) {
  return new Date(ts * 1000).toLocaleString()
}

function Timestamp({ ts }: { ts: number }) {
  return (
    <span title={absoluteTime(ts)}>{formatTimeAgo(new Date(ts * 1000))}</span>
  )
}

function buildQuery(filters: Filters, tab: HistoryTab, page: number, perPage: number) {
  const p = new URLSearchParams()
  if (filters.preset === 'custom') {
    if (filters.startDate) p.set('start_date', filters.startDate)
    if (filters.endDate) p.set('end_date', filters.endDate)
  } else {
    p.set('preset', filters.preset)
  }
  if (filters.type) p.set('type', filters.type)
  if (filters.hostname.trim()) p.set('hostname', filters.hostname.trim())
  if (filters.service.trim()) p.set('service', filters.service.trim())
  if (tab === 'alerts') {
    if (filters.state) p.set('new_state', filters.state)
    if (filters.stateType) p.set('state_type', filters.stateType)
    if (filters.ack !== 'all') p.set('ack_filter', filters.ack)
  } else {
    if (filters.state) p.set('state', filters.state)
    if (filters.contact.trim()) p.set('contact', filters.contact.trim())
    if (filters.source) p.set('source', filters.source)
  }
  p.set('page', String(page))
  p.set('per_page', String(perPage))
  return p.toString()
}

function detailQuery(
  event: { hostname: string; service_name: string | null; timestamp: number; source?: string; id?: number },
  newState?: string
) {
  const p = new URLSearchParams({ hostname: event.hostname, timestamp: String(event.timestamp) })
  if (event.source === 'pinpoint') {
    p.set('source', 'pinpoint')
    p.set('id', String(event.id ?? 0))
  }
  if (event.service_name) p.set('service', event.service_name)
  if (newState) p.set('new_state', newState)
  return p.toString()
}

export function HistoryPage() {
  const [tab, setTab] = useState<HistoryTab>('alerts')
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [applied, setApplied] = useState<Filters>(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(25)

  const [alerts, setAlerts] = useState<Page<AlertEvent> | null>(null)
  const [notifications, setNotifications] = useState<Page<NotificationEvent> | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [loadedAt, setLoadedAt] = useState<Date | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [alertDetail, setAlertDetail] = useState<AlertDetail | null>(null)
  const [notificationDetail, setNotificationDetail] = useState<NotificationDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const requestId = useRef(0)

  const load = useCallback(async () => {
    const thisRequest = ++requestId.current
    if (applied.preset === 'custom' && (!applied.startDate || !applied.endDate)) {
      setLoadError('Pick a start and end date for a custom range.')
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    setLoadError(null)
    try {
      const qs = buildQuery(applied, tab, page, perPage)
      if (tab === 'alerts') {
        const result = await apiGet<Page<AlertEvent>>(`/api/system/history/alerts?${qs}`)
        if (thisRequest === requestId.current) setAlerts(result)
      } else {
        const result = await apiGet<Page<NotificationEvent>>(`/api/system/history/notifications?${qs}`)
        if (thisRequest === requestId.current) setNotifications(result)
      }
      if (thisRequest === requestId.current) setLoadedAt(new Date())
    } catch (err) {
      if (thisRequest === requestId.current) setLoadError(errorMessage(err, 'Unable to load history.'))
    } finally {
      if (thisRequest === requestId.current) setIsLoading(false)
    }
  }, [applied, tab, page, perPage])

  useEffect(() => {
    load()
  }, [load])

  function switchTab(next: HistoryTab) {
    setTab(next)
    setPage(1)
    setExpanded(null)
    setFilters({ ...EMPTY_FILTERS, preset: filters.preset, startDate: filters.startDate, endDate: filters.endDate })
    setApplied({ ...EMPTY_FILTERS, preset: filters.preset, startDate: filters.startDate, endDate: filters.endDate })
  }

  function applyFilters() {
    setPage(1)
    setExpanded(null)
    setApplied(filters)
  }

  function clearFilters() {
    setFilters(EMPTY_FILTERS)
    setApplied(EMPTY_FILTERS)
    setPage(1)
    setExpanded(null)
  }

  async function toggleAlert(event: AlertEvent) {
    const key = `a-${event.hostname}-${event.service_name}-${event.timestamp}-${event.new_state}`
    if (expanded === key) {
      setExpanded(null)
      return
    }
    setExpanded(key)
    setAlertDetail(null)
    setDetailError(null)
    try {
      setAlertDetail(
        await apiGet<AlertDetail>(`/api/system/history/alerts/detail?${detailQuery(event, event.new_state)}`)
      )
    } catch (err) {
      setDetailError(errorMessage(err, 'Unable to load event detail.'))
    }
  }

  async function toggleNotification(event: NotificationEvent) {
    const key = `n-${event.source}-${event.id ?? ''}-${event.hostname}-${event.service_name}-${event.timestamp}-${event.contact}`
    if (expanded === key) {
      setExpanded(null)
      return
    }
    setExpanded(key)
    setNotificationDetail(null)
    setDetailError(null)
    try {
      setNotificationDetail(
        await apiGet<NotificationDetail>(`/api/system/history/notifications/detail?${detailQuery(event)}`)
      )
    } catch (err) {
      setDetailError(errorMessage(err, 'Unable to load notification detail.'))
    }
  }

  const data = tab === 'alerts' ? alerts : notifications
  const hasFilters = JSON.stringify(applied) !== JSON.stringify(EMPTY_FILTERS)
  const rangeStart = data && data.total > 0 ? (data.page - 1) * data.per_page + 1 : 0
  const rangeEnd = data ? Math.min(data.page * data.per_page, data.total) : 0
  const colSpan = tab === 'alerts' ? 9 : 9

  return (
    <main className="ml-55 flex-1">
      <div className="space-y-6 p-6">
        <PageHeader
          title="History"
          highlight={tab === 'alerts' ? 'Alerts' : 'Notifications'}
          description="Browse past state changes and the notifications raised by Nagios and by Pinpoint (such as network scan results)."
        />

        <div className="flex gap-6 border-b border-[var(--border)]">
          {(['alerts', 'notifications'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => switchTab(t)}
              className={`pb-3 text-sm transition ${
                tab === t
                  ? 'border-b-2 border-[var(--text)] font-medium text-[var(--text)]'
                  : 'text-[var(--text-muted)] hover:text-[var(--text)]'
              }`}
            >
              {t === 'alerts' ? 'Alerts History' : 'Notifications History'}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4">
          <select
            aria-label="Time range"
            value={filters.preset}
            onChange={(e) => setFilters({ ...filters, preset: e.target.value })}
            className={CONTROL_CLASS}
          >
            {PRESETS.map((p) => (
              <option key={p.value} value={p.value} className="bg-[var(--card)]">{p.label}</option>
            ))}
          </select>
          {filters.preset === 'custom' && (
            <>
              <input
                type="date"
                aria-label="Start date"
                value={filters.startDate}
                onChange={(e) => setFilters({ ...filters, startDate: e.target.value })}
                className={CONTROL_CLASS}
              />
              <input
                type="date"
                aria-label="End date"
                value={filters.endDate}
                onChange={(e) => setFilters({ ...filters, endDate: e.target.value })}
                className={CONTROL_CLASS}
              />
            </>
          )}
          <select
            aria-label="Type"
            value={filters.type}
            onChange={(e) => setFilters({ ...filters, type: e.target.value })}
            className={CONTROL_CLASS}
          >
            <option value="" className="bg-[var(--card)]">All types</option>
            <option value="host" className="bg-[var(--card)]">Host only</option>
            <option value="service" className="bg-[var(--card)]">Service only</option>
          </select>
          <input
            placeholder="Host"
            aria-label="Host"
            value={filters.hostname}
            onChange={(e) => setFilters({ ...filters, hostname: e.target.value })}
            className={`${CONTROL_CLASS} w-36`}
          />
          <input
            placeholder="Service"
            aria-label="Service"
            value={filters.service}
            onChange={(e) => setFilters({ ...filters, service: e.target.value })}
            className={`${CONTROL_CLASS} w-36`}
          />
          <select
            aria-label={tab === 'alerts' ? 'New state' : 'State'}
            value={filters.state}
            onChange={(e) => setFilters({ ...filters, state: e.target.value })}
            className={CONTROL_CLASS}
          >
            <option value="" className="bg-[var(--card)]">{tab === 'alerts' ? 'Any new state' : 'Any state'}</option>
            {(tab === 'alerts' ? STATE_OPTIONS : [...STATE_OPTIONS, ...PINPOINT_STATE_OPTIONS]).map((s) => (
              <option key={s} value={s} className="bg-[var(--card)]">{s}</option>
            ))}
          </select>
          {tab === 'alerts' ? (
            <>
              <select
                aria-label="State type"
                value={filters.stateType}
                onChange={(e) => setFilters({ ...filters, stateType: e.target.value })}
                className={CONTROL_CLASS}
              >
                <option value="" className="bg-[var(--card)]">Hard &amp; soft</option>
                <option value="hard" className="bg-[var(--card)]">Hard only</option>
                <option value="soft" className="bg-[var(--card)]">Soft only</option>
              </select>
              <select
                aria-label="Acknowledged"
                value={filters.ack}
                onChange={(e) => setFilters({ ...filters, ack: e.target.value })}
                className={CONTROL_CLASS}
              >
                <option value="all" className="bg-[var(--card)]">All acknowledgement</option>
                <option value="acknowledged" className="bg-[var(--card)]">Acknowledged only</option>
                <option value="unacknowledged" className="bg-[var(--card)]">Unacknowledged only</option>
              </select>
            </>
          ) : (
            <>
              <select
                aria-label="Source"
                value={filters.source}
                onChange={(e) => setFilters({ ...filters, source: e.target.value })}
                className={CONTROL_CLASS}
              >
                <option value="" className="bg-[var(--card)]">All sources</option>
                <option value="nagios" className="bg-[var(--card)]">Nagios</option>
                <option value="pinpoint" className="bg-[var(--card)]">Pinpoint</option>
              </select>
            <input
              placeholder="Contact"
              aria-label="Contact"
              value={filters.contact}
              onChange={(e) => setFilters({ ...filters, contact: e.target.value })}
              className={`${CONTROL_CLASS} w-36`}
            />
            </>
          )}
          <button
            type="button"
            onClick={applyFilters}
            className="h-10 rounded-xl bg-[#ffb100] px-4 text-sm font-semibold text-black"
          >
            Apply
          </button>
          <button
            type="button"
            onClick={clearFilters}
            className="h-10 rounded-xl border border-[var(--border)] px-4 text-sm text-[var(--text)] hover:bg-[var(--hover)]"
          >
            Clear filters
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-[var(--text-muted)]">
          <span>
            {data && data.total > 0
              ? `Showing ${rangeStart}–${rangeEnd} of ${data.total} ${tab === 'alerts' ? 'events' : 'notifications'}`
              : ''}
          </span>
          <div className="flex items-center gap-3">
            {loadedAt && <span>Loaded {loadedAt.toLocaleTimeString()}</span>}
            <select
              aria-label="Rows per page"
              value={perPage}
              onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1) }}
              className={CONTROL_CLASS}
            >
              {[25, 50, 100].map((n) => (
                <option key={n} value={n} className="bg-[var(--card)]">{n} per page</option>
              ))}
            </select>
            <button
              type="button"
              onClick={load}
              disabled={isLoading}
              className="flex h-10 items-center gap-2 rounded-xl border border-[var(--border)] px-4 text-[var(--text)] hover:bg-[var(--hover)] disabled:opacity-60"
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Refresh
            </button>
          </div>
        </div>

        {loadError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-600 dark:text-red-400">
            {loadError}
          </div>
        )}

        <div className="overflow-x-auto rounded-2xl border border-[var(--border)] bg-[var(--card)]">
          <table className="w-full text-left text-sm text-[var(--text)]">
            <thead className="border-b border-[var(--border)] text-xs uppercase tracking-wide text-[var(--text-muted)]">
              {tab === 'alerts' ? (
                <tr>
                  <th className="w-8 px-3 py-3" />
                  <th className="px-3 py-3">Time</th>
                  <th className="px-3 py-3">Type</th>
                  <th className="px-3 py-3">Host</th>
                  <th className="px-3 py-3">Service</th>
                  <th className="px-3 py-3">Previous → New</th>
                  <th className="px-3 py-3">State type</th>
                  <th className="px-3 py-3">Time in previous state</th>
                  <th className="px-3 py-3">Output</th>
                </tr>
              ) : (
                <tr>
                  <th className="w-8 px-3 py-3" />
                  <th className="px-3 py-3">Time</th>
                  <th className="px-3 py-3">Source</th>
                  <th className="px-3 py-3">Type</th>
                  <th className="px-3 py-3">Host</th>
                  <th className="px-3 py-3">Service</th>
                  <th className="px-3 py-3">State</th>
                  <th className="px-3 py-3">Contact</th>
                  <th className="px-3 py-3">Method / message</th>
                </tr>
              )}
            </thead>
            <tbody>
              {isLoading && !data && (
                <tr><td colSpan={colSpan} className="px-4 py-10 text-center text-[var(--text-muted)]">Loading…</td></tr>
              )}
              {data && data.items.length === 0 && !isLoading && (
                <tr>
                  <td colSpan={colSpan} className="px-4 py-10 text-center text-[var(--text-muted)]">
                    {hasFilters ? (
                      <>
                        No events match the current filters.{' '}
                        <button type="button" onClick={clearFilters} className="underline">Clear filters</button>
                      </>
                    ) : tab === 'alerts' ? (
                      'No alert history is available yet. Events will appear here as hosts and services change state.'
                    ) : (
                      'No notification history is available yet.'
                    )}
                  </td>
                </tr>
              )}

              {tab === 'alerts' && alerts?.items.map((a) => {
                const key = `a-${a.hostname}-${a.service_name}-${a.timestamp}-${a.new_state}`
                const open = expanded === key
                return (
                  <FragmentRows key={key}>
                    <tr
                      onClick={() => toggleAlert(a)}
                      className="cursor-pointer border-b border-[var(--border)] hover:bg-[var(--hover)]"
                    >
                      <td className="px-3 py-3 text-[var(--text-muted)]">
                        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3"><Timestamp ts={a.timestamp} /></td>
                      <td className="px-3 py-3 capitalize">{a.type}</td>
                      <td className="px-3 py-3">{a.hostname}</td>
                      <td className="px-3 py-3">{a.service_name ?? '—'}</td>
                      <td className="whitespace-nowrap px-3 py-3">
                        <StateBadge state={a.previous_state} /> → <StateBadge state={a.new_state} />
                        {a.acknowledged && (
                          <span className="ml-2 rounded-full bg-blue-500/15 px-2 py-0.5 text-xs text-blue-600 dark:text-blue-400">
                            Acked
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-3 capitalize">{a.state_type || '—'}</td>
                      <td className="px-3 py-3">{formatDuration(a.duration_seconds)}</td>
                      <td className="max-w-xs truncate px-3 py-3 text-[var(--text-muted)]">{a.plugin_output}</td>
                    </tr>
                    {open && (
                      <tr className="border-b border-[var(--border)] bg-[var(--card-alt)]">
                        <td colSpan={colSpan} className="px-6 py-4">
                          {detailError && <p className="text-sm text-red-500">{detailError}</p>}
                          {!detailError && !alertDetail && <p className="text-sm text-[var(--text-muted)]">Loading detail…</p>}
                          {alertDetail && (
                            <div className="space-y-3 text-sm">
                              <p className="text-xs text-[var(--text-muted)]">{absoluteTime(alertDetail.timestamp)}</p>
                              <div>
                                <p className="mb-1 font-medium">Plugin output</p>
                                <pre className="whitespace-pre-wrap break-words font-mono text-xs text-[var(--text-muted)]">
                                  {alertDetail.plugin_output || '—'}
                                </pre>
                              </div>
                              {alertDetail.recovery_duration != null && (
                                <p>Time in problem state before recovery: <strong>{formatDuration(alertDetail.recovery_duration)}</strong></p>
                              )}
                              {alertDetail.ack && (
                                <p>
                                  Acknowledged by <strong>{alertDetail.ack.acknowledged_by ?? 'unknown'}</strong> on{' '}
                                  {new Date(alertDetail.ack.acknowledged_at).toLocaleString()}
                                  {alertDetail.ack.comment ? ` — “${alertDetail.ack.comment}”` : ''}
                                </p>
                              )}
                              <div>
                                <p className="mb-1 font-medium">Related notifications</p>
                                {alertDetail.linked_notifications.length === 0 ? (
                                  <p className="text-[var(--text-muted)]">No notifications were sent for this alert.</p>
                                ) : (
                                  <ul className="space-y-1">
                                    {alertDetail.linked_notifications.map((n, i) => (
                                      <li key={i} className="text-[var(--text-muted)]">
                                        <Timestamp ts={n.timestamp} /> · <StateBadge state={n.state} /> · {n.contact}
                                        {n.message ? ` — ${n.message}` : ''}
                                      </li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </FragmentRows>
                )
              })}

              {tab === 'notifications' && notifications?.items.map((n) => {
                const key = `n-${n.source}-${n.id ?? ''}-${n.hostname}-${n.service_name}-${n.timestamp}-${n.contact}`
                const open = expanded === key
                return (
                  <FragmentRows key={key}>
                    <tr
                      onClick={() => toggleNotification(n)}
                      className="cursor-pointer border-b border-[var(--border)] hover:bg-[var(--hover)]"
                    >
                      <td className="px-3 py-3 text-[var(--text-muted)]">
                        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      </td>
                      <td className="whitespace-nowrap px-3 py-3"><Timestamp ts={n.timestamp} /></td>
                      <td className="px-3 py-3"><SourceBadge source={n.source} /></td>
                      <td className="px-3 py-3 capitalize">{n.type === 'scan' ? 'Network scan' : n.type}</td>
                      <td className="px-3 py-3">{n.hostname}</td>
                      <td className="px-3 py-3">{n.service_name ?? '—'}</td>
                      <td className="px-3 py-3"><StateBadge state={n.state} /></td>
                      <td className="px-3 py-3">{n.contact || '—'}</td>
                      <td className="max-w-xs truncate px-3 py-3 text-[var(--text-muted)]">
                        {[n.method, n.message].filter(Boolean).join(' · ')}
                      </td>
                    </tr>
                    {open && (
                      <tr className="border-b border-[var(--border)] bg-[var(--card-alt)]">
                        <td colSpan={colSpan} className="px-6 py-4">
                          {detailError && <p className="text-sm text-red-500">{detailError}</p>}
                          {!detailError && !notificationDetail && <p className="text-sm text-[var(--text-muted)]">Loading detail…</p>}
                          {notificationDetail && (
                            <div className="space-y-3 text-sm">
                              <p className="text-xs text-[var(--text-muted)]">{absoluteTime(notificationDetail.timestamp)}</p>
                              <div>
                                <p className="mb-1 font-medium">Message</p>
                                <pre className="whitespace-pre-wrap break-words font-mono text-xs text-[var(--text-muted)]">
                                  {notificationDetail.message || '—'}
                                </pre>
                              </div>
                              {n.source === 'pinpoint' ? null : (
                                <p>Contacts notified: <strong>{notificationDetail.contacts.join(', ') || '—'}</strong></p>
                              )}
                              {n.source === 'pinpoint' ? null : notificationDetail.linked_alert ? (
                                <p>
                                  Related alert:{' '}
                                  <StateBadge state={notificationDetail.linked_alert.prev_state} /> →{' '}
                                  <StateBadge state={notificationDetail.linked_alert.new_state} />{' '}
                                  <button
                                    type="button"
                                    className="ml-2 underline"
                                    onClick={() => {
                                      setFilters({ ...EMPTY_FILTERS, hostname: n.hostname, service: n.service_name ?? '' })
                                      setApplied({ ...EMPTY_FILTERS, hostname: n.hostname, service: n.service_name ?? '' })
                                      setTab('alerts')
                                      setPage(1)
                                      setExpanded(null)
                                    }}
                                  >
                                    View in Alerts History
                                  </button>
                                </p>
                              ) : (
                                <p className="text-[var(--text-muted)]">No matching alert event was found.</p>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </FragmentRows>
                )
              })}
            </tbody>
          </table>
        </div>

        {data && data.pages > 1 && (
          <div className="flex items-center justify-end gap-3 text-sm text-[var(--text)]">
            <button
              type="button"
              disabled={page <= 1 || isLoading}
              onClick={() => setPage(page - 1)}
              className="rounded-xl border border-[var(--border)] px-4 py-2 hover:bg-[var(--hover)] disabled:opacity-50"
            >
              Previous
            </button>
            <span>Page {data.page} of {data.pages}</span>
            <button
              type="button"
              disabled={page >= data.pages || isLoading}
              onClick={() => setPage(page + 1)}
              className="rounded-xl border border-[var(--border)] px-4 py-2 hover:bg-[var(--hover)] disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </main>
  )
}

function FragmentRows({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
