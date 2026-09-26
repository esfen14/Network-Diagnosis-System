import { useEffect, useMemo, useState } from 'react'
import { Activity, CheckCircle2, XCircle } from 'lucide-react'
import { HostTable } from '../components/device-inventory/HostTable'
import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { useSystemSettings } from '../contexts/SystemSettingsContext'
import { apiDelete, apiGet, apiPost, errorMessage } from '../lib/api'
import { fromHostRecord, type Host, type HostListResponse, type HostState } from '../types/host'

const PER_PAGE = 10

function buildQuery(params: Record<string, string | number>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== undefined) search.set(key, String(value))
  })
  return search.toString()
}

export function DeviceInventoryPage() {
  const { settings } = useSystemSettings()
  const isLight = settings.theme === 'light'

  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [stateFilter, setStateFilter] = useState<'All' | HostState>('All')
  const [showFilter, setShowFilter] = useState(false)
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(1)

  const [hosts, setHosts] = useState<Host[]>([])
  const [listMeta, setListMeta] = useState({ pages: 1, total: 0, hasNext: false, hasPrev: false })
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [counts, setCounts] = useState({ total: 0, up: 0 })

  const [ackTarget, setAckTarget] = useState<Host | null>(null)

  useEffect(() => {
    const timeout = setTimeout(() => {
      setDebouncedQuery(query)
      setPage(1)
    }, 350)
    return () => clearTimeout(timeout)
  }, [query])

  useEffect(() => {
    setPage(1)
  }, [stateFilter, sortAsc])

  async function loadHosts() {
    setIsLoading(true)
    setLoadError(null)
    try {
      const qs = buildQuery({
        page,
        per_page: PER_PAGE,
        sort_by: 'hostname',
        order: sortAsc ? 'asc' : 'desc',
        search: debouncedQuery,
        state: stateFilter === 'All' ? '' : stateFilter,
      })
      const data = await apiGet<HostListResponse>(`/api/system/network-health/hosts?${qs}`)
      setHosts(data.items.map(fromHostRecord))
      setListMeta({ pages: data.pages, total: data.total, hasNext: data.has_next, hasPrev: data.has_prev })
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load hosts.'))
    } finally {
      setIsLoading(false)
    }
  }

  async function loadCounts() {
    try {
      const [totalRes, upRes] = await Promise.all([
        apiGet<HostListResponse>(`/api/system/network-health/hosts?${buildQuery({ per_page: 1 })}`),
        apiGet<HostListResponse>(`/api/system/network-health/hosts?${buildQuery({ per_page: 1, state: 'UP' })}`),
      ])
      setCounts({ total: totalRes.total, up: upRes.total })
    } catch {
      // Non-fatal — summary cards just won't update.
    }
  }

  useEffect(() => {
    loadHosts()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, debouncedQuery, stateFilter, sortAsc])

  useEffect(() => {
    loadCounts()
  }, [])

  const hostTotals = useMemo(
    () => ({ total: counts.total, online: counts.up, offline: Math.max(0, counts.total - counts.up) }),
    [counts]
  )

  async function acknowledgeHost(host: Host, comment: string) {
    try {
      await apiPost('/api/system/network-health/hosts/acknowledge', { hostname: host.hostname, comment })
      setAckTarget(null)
      await Promise.all([loadHosts(), loadCounts()])
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to acknowledge host.'))
    }
  }

  async function unacknowledgeHost(host: Host) {
    try {
      await apiDelete('/api/system/network-health/hosts/acknowledge', { hostname: host.hostname })
      await loadHosts()
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to remove acknowledgement.'))
    }
  }

  return (
    <main
      className={`ml-55 flex-1 ${
        isLight
          ? 'bg-[#f5f6f8] text-gray-900'
          : 'bg-pinpoint-dark text-white'
      }`}
    >
      <div className="space-y-6">

        <PageHeader
          title="Host Inventory"
          highlight="All Hosts"
          description="Live Nagios host status for every monitored device in your network infrastructure."
        />

        {loadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
            {loadError}
          </div>
        )}

        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
          <SummaryStatCard
            title="Total Hosts"
            value={String(hostTotals.total)}
            subtitle="Across the network"
            icon={Activity}
            gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
          />

          <SummaryStatCard
            title="Up"
            value={String(hostTotals.online)}
            subtitle="Currently reachable"
            icon={CheckCircle2}
            gradient="linear-gradient(135deg,#22C55E,#16A34A)"
          />

          <SummaryStatCard
            title="Down / Unreachable"
            value={String(hostTotals.offline)}
            subtitle="Needs attention"
            icon={XCircle}
            gradient="linear-gradient(135deg,#EF4444,#DC2626)"
          />
        </div>

        <HostTable
          hosts={hosts}
          title="All Hosts"
          isLoading={isLoading}
          query={query}
          onQueryChange={setQuery}
          stateFilter={stateFilter}
          onStateFilterChange={(s) => { setStateFilter(s); setShowFilter(false) }}
          showFilter={showFilter}
          onToggleFilter={() => setShowFilter((v) => !v)}
          sortAsc={sortAsc}
          onToggleSort={() => setSortAsc((v) => !v)}
          page={page}
          pageCount={listMeta.pages}
          total={listMeta.total}
          hasNext={listMeta.hasNext}
          hasPrev={listMeta.hasPrev}
          onPageChange={setPage}
          onAcknowledge={(host) => setAckTarget(host)}
          onUnacknowledge={unacknowledgeHost}
        />
      </div>

      {ackTarget && (
        <AcknowledgeModal
          host={ackTarget}
          onCancel={() => setAckTarget(null)}
          onConfirm={(comment) => acknowledgeHost(ackTarget, comment)}
        />
      )}
    </main>
  )
}

function AcknowledgeModal({
  host,
  onCancel,
  onConfirm,
}: {
  host: Host
  onCancel: () => void
  onConfirm: (comment: string) => void
}) {
  const [comment, setComment] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  const handleConfirm = async () => {
    if (!comment.trim()) return
    setIsSaving(true)
    try {
      await onConfirm(comment.trim())
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl dark:bg-[#171B20]">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          Acknowledge {host.hostname}
        </h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Add a comment explaining the acknowledgement.
        </p>

        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={3}
          placeholder="e.g. Investigating with the network team"
          className="mt-4 w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-white/20 dark:bg-[#0D1117] dark:text-white"
        />

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!comment.trim() || isSaving}
            className="rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving ? 'Saving…' : 'Acknowledge'}
          </button>
        </div>
      </div>
    </div>
  )
}
