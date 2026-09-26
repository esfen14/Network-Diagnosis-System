import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from 'lucide-react'
import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { ServiceStatusTable } from '../components/system-status/ServiceStatusTable'
import { apiDelete, apiGet, apiPost, errorMessage } from '../lib/api'
import { fromServiceRecord, type ServiceListResponse, type ServiceRow, type ServiceState } from '../types/service'

const PER_PAGE = 10
const POLL_INTERVAL_MS = 90_000 // matches the ~90s cadence the old mock comment referenced

type ServiceCounts = { total: number; ok: number; warning: number; critical: number; unknown: number }

function buildQuery(params: Record<string, string | number>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== undefined) search.set(key, String(value))
  })
  return search.toString()
}

export function TopologyPage() {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [stateFilter, setStateFilter] = useState<'All' | ServiceState>('All')
  const [showFilter, setShowFilter] = useState(false)
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(1)

  const [services, setServices] = useState<ServiceRow[]>([])
  const [listMeta, setListMeta] = useState({ pages: 1, total: 0, hasNext: false, hasPrev: false })
  const [counts, setCounts] = useState<ServiceCounts>({ total: 0, ok: 0, warning: 0, critical: 0, unknown: 0 })
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [ackTarget, setAckTarget] = useState<ServiceRow | null>(null)

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

  async function loadServices() {
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
      const data = await apiGet<ServiceListResponse>(`/api/system/network-health/services?${qs}`)
      setServices(data.items.map(fromServiceRecord))
      setListMeta({ pages: data.pages, total: data.total, hasNext: data.has_next, hasPrev: data.has_prev })
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load services.'))
    } finally {
      setIsLoading(false)
    }
  }

  async function loadCounts() {
    try {
      const data = await apiGet<{ services: ServiceCounts }>('/api/system/dashboard/summary')
      setCounts(data.services)
    } catch {
      // Non-fatal — summary cards just won't update.
    }
  }

  useEffect(() => {
    loadServices()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, debouncedQuery, stateFilter, sortAsc])

  useEffect(() => {
    loadCounts()
    const id = window.setInterval(loadCounts, POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [])

  async function acknowledgeService(service: ServiceRow, comment: string) {
    try {
      await apiPost('/api/system/network-health/services/acknowledge', {
        hostname: service.hostname,
        service_name: service.service,
        comment,
      })
      setAckTarget(null)
      await Promise.all([loadServices(), loadCounts()])
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to acknowledge service.'))
    }
  }

  async function unacknowledgeService(service: ServiceRow) {
    try {
      await apiDelete('/api/system/network-health/services/acknowledge', {
        hostname: service.hostname,
        service_name: service.service,
      })
      await loadServices()
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to remove acknowledgement.'))
    }
  }

  return (
    <main className="ml-[220px] flex-1">
      <div className="space-y-6">

        <PageHeader
          title="Service Status"
          highlight="Overview"
          description="Live status of hosts and monitored services across your network."
        />

        {loadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
            {loadError}
          </div>
        )}

        <div className="grid grid-cols-1 gap-5 md:grid-cols-4">
          <SummaryStatCard
            title="OK"
            value={String(counts.ok)}
            subtitle="Running normally"
            icon={CheckCircle2}
            gradient="linear-gradient(135deg,#22C55E,#16A34A)"
          />
          <SummaryStatCard
            title="Warning"
            value={String(counts.warning)}
            subtitle="Needs attention"
            icon={AlertTriangle}
            gradient="linear-gradient(135deg,#EAB308,#CA8A04)"
          />
          <SummaryStatCard
            title="Unknown"
            value={String(counts.unknown)}
            subtitle="Check inconclusive"
            icon={HelpCircle}
            gradient="linear-gradient(135deg,#FF8A00,#FF5C00)"
          />
          <SummaryStatCard
            title="Critical"
            value={String(counts.critical)}
            subtitle="Service down"
            icon={XCircle}
            gradient="linear-gradient(135deg,#EF4444,#DC2626)"
          />
        </div>

        <ServiceStatusTable
          services={services}
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
          onAcknowledge={(service) => setAckTarget(service)}
          onUnacknowledge={unacknowledgeService}
        />

      </div>

      {ackTarget && (
        <AcknowledgeModal
          service={ackTarget}
          onCancel={() => setAckTarget(null)}
          onConfirm={(comment) => acknowledgeService(ackTarget, comment)}
        />
      )}
    </main>
  )
}

function AcknowledgeModal({
  service,
  onCancel,
  onConfirm,
}: {
  service: ServiceRow
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
          Acknowledge {service.hostname} / {service.service}
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
