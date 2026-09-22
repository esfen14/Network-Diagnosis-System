import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertTriangle, Boxes, CheckCircle2, PackagePlus, Puzzle, RefreshCcw } from 'lucide-react'
import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { PluginInventoryTable } from '../components/plugin-manager/PluginInventoryTable'
import { PluginDetailsDrawer } from '../components/plugin-manager/PluginDetailsDrawer'
import { AddCustomPluginModal } from '../components/plugin-manager/AddCustomPluginModal'
import { errorMessage } from '../lib/api'
import { getPluginInventory, getPluginScanStatus, getPluginSummary, startPluginScan } from '../lib/pluginApi'
import type { PluginListItem, PluginStatus, PluginSummary, PluginType } from '../types/plugin'

const PER_PAGE = 10

export function PluginsPage() {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<'All' | PluginType>('All')
  const [statusFilter, setStatusFilter] = useState<'All' | PluginStatus | 'Failed'>('All')
  const [showFilter, setShowFilter] = useState(false)
  const [sortAsc, setSortAsc] = useState(true)
  const [page, setPage] = useState(1)

  const [plugins, setPlugins] = useState<PluginListItem[]>([])
  const [listMeta, setListMeta] = useState({ pages: 1, total: 0, hasNext: false, hasPrev: false })
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [summary, setSummary] = useState<PluginSummary | null>(null)

  const [isScanning, setIsScanning] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [selectedPluginId, setSelectedPluginId] = useState<number | null>(null)
  const [showAddCustom, setShowAddCustom] = useState(false)

  useEffect(() => {
    const timeout = setTimeout(() => {
      setDebouncedQuery(query)
      setPage(1)
    }, 350)
    return () => clearTimeout(timeout)
  }, [query])

  useEffect(() => {
    setPage(1)
  }, [typeFilter, statusFilter, sortAsc])

  const loadInventory = useCallback(async () => {
    setIsLoading(true)
    setLoadError(null)
    try {
      const data = await getPluginInventory({
        page,
        per_page: PER_PAGE,
        sort_by: 'name',
        order: sortAsc ? 'asc' : 'desc',
        search: debouncedQuery,
        type: typeFilter === 'All' ? undefined : typeFilter,
        status: statusFilter === 'All' ? undefined : statusFilter,
      })
      setPlugins(data.items)
      setListMeta({ pages: data.pages, total: data.total, hasNext: data.has_next, hasPrev: data.has_prev })
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load plugin inventory.'))
    } finally {
      setIsLoading(false)
    }
  }, [page, sortAsc, debouncedQuery, typeFilter, statusFilter])

  const loadSummary = useCallback(async () => {
    try {
      setSummary(await getPluginSummary())
    } catch {
      // Non-fatal — summary cards just won't update.
    }
  }, [])

  useEffect(() => {
    loadInventory()
  }, [loadInventory])

  useEffect(() => {
    loadSummary()
  }, [loadSummary])

  const refreshAll = useCallback(() => {
    loadInventory()
    loadSummary()
  }, [loadInventory, loadSummary])

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const handleScan = async () => {
    setScanError(null)
    setIsScanning(true)
    try {
      await startPluginScan()
      pollRef.current = setInterval(async () => {
        try {
          const status = await getPluginScanStatus()
          if (!status || status.status !== 'Running') {
            stopPolling()
            setIsScanning(false)
            if (status?.status === 'Failed') {
              setScanError(status.error ?? 'Plugin scan failed.')
            }
            refreshAll()
          }
        } catch (err) {
          stopPolling()
          setIsScanning(false)
          setScanError(errorMessage(err, 'Unable to check scan status.'))
        }
      }, 1500)
    } catch (err) {
      setIsScanning(false)
      setScanError(errorMessage(err, 'Unable to start plugin scan.'))
    }
  }

  useEffect(() => stopPolling, [])

  return (
    <main className="ml-55 flex-1 space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          title="Plugin Manager"
          description="Manage Nagios plugin executables and command definitions on this server."
        />
        <button
          type="button"
          onClick={() => setShowAddCustom(true)}
          className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-200 dark:hover:bg-white/10"
        >
          <PackagePlus className="h-4 w-4" /> Add Custom Plugin
        </button>
      </div>

      {loadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
          {loadError}
        </div>
      )}
      {scanError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
          {scanError}
        </div>
      )}

      <div className="grid md:grid-cols-5 gap-5">
        <SummaryStatCard
          title="Installed Plugins"
          value={summary ? String(summary.installed_plugins) : '—'}
          subtitle="in inventory"
          icon={Boxes}
          gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
        />
        <SummaryStatCard
          title="Active Capabilities"
          value={summary ? String(summary.active_capabilities) : '—'}
          subtitle="live monitoring checks"
          icon={CheckCircle2}
          gradient="linear-gradient(135deg,#22C55E,#16A34A)"
        />
        <SummaryStatCard
          title="Custom Plugins"
          value={summary ? String(summary.custom_plugins) : '—'}
          subtitle="administrator added"
          icon={Puzzle}
          gradient="linear-gradient(135deg,#FF8A00,#FF5C00)"
        />
        <SummaryStatCard
          title="Updates Available"
          value={summary ? String(summary.updates_available) : '—'}
          subtitle="newer version found"
          icon={RefreshCcw}
          gradient="linear-gradient(135deg,#3B82F6,#2563EB)"
        />
        <SummaryStatCard
          title="Validation Issues"
          value={summary ? String(summary.validation_issues) : '—'}
          subtitle="need attention"
          icon={AlertTriangle}
          gradient="linear-gradient(135deg,#FF4D4D,#DC2626)"
        />
      </div>

      <PluginInventoryTable
        plugins={plugins}
        isLoading={isLoading}
        query={query}
        onQueryChange={setQuery}
        typeFilter={typeFilter}
        onTypeFilterChange={(t) => { setTypeFilter(t); setShowFilter(false) }}
        statusFilter={statusFilter}
        onStatusFilterChange={(s) => { setStatusFilter(s); setShowFilter(false) }}
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
        onSelectPlugin={(plugin) => setSelectedPluginId(plugin.id)}
        onScan={handleScan}
        isScanning={isScanning}
      />

      {selectedPluginId !== null && (
        <PluginDetailsDrawer
          pluginId={selectedPluginId}
          onClose={() => setSelectedPluginId(null)}
          onChanged={refreshAll}
        />
      )}

      {showAddCustom && (
        <AddCustomPluginModal
          onClose={() => setShowAddCustom(false)}
          onAdded={refreshAll}
        />
      )}
    </main>
  )
}
