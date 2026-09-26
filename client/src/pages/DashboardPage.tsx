import { useEffect, useState } from 'react'
import { AlertTriangle, Gauge, Server, Wifi } from 'lucide-react'
import { NetworkPerformanceSection } from '../components/dashboard/NetworkPerformanceSection'
import { NetworkStatusOverview } from '../components/dashboard/NetworkStatusOverview'
import { RecentOutageTable } from '../components/dashboard/RecentOutageTable'
import { RescanButton } from '../components/dashboard/RescanButton'
import { ResourceUtilizationSection, type TrendHours } from '../components/dashboard/ResourceUtilizationSection'
import { ServiceOverview } from '../components/dashboard/ServiceOverview'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { useSystemSettings } from '../contexts/SystemSettingsContext'
import { formatDateTime } from '../utils/formatDateTime'
import { apiGet, apiPost, errorMessage } from '../lib/api'
import {
  fromAlertRecord,
  fromDashboardStatusResponse,
  fromDashboardSummaryResponse,
  fromTrendsResponse,
  type AlertRow,
  type DashboardStatus,
  type DashboardSummary,
  type TrendsResponse,
} from '../types/dashboard'
import { fromServiceRecord, type ServiceListResponse, type ServiceRow } from '../types/service'

const SEVERITY_RANK: Record<string, number> = { CRITICAL: 0, WARNING: 1, UNKNOWN: 2, OK: 3 }

export function DashboardPage() {
  const { settings } = useSystemSettings()
  const [lastRefreshed, setLastRefreshed] = useState(() => new Date())

  const [status, setStatus] = useState<DashboardStatus | null>(null)
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [alerts, setAlerts] = useState<AlertRow[]>([])
  const [trends, setTrends] = useState<TrendsResponse | null>(null)
  const [problemServices, setProblemServices] = useState<ServiceRow[]>([])
  const [trendHours, setTrendHours] = useState<TrendHours>(24)

  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [ackTarget, setAckTarget] = useState<AlertRow | null>(null)

  async function loadAll() {
    setLoadError(null)
    try {
      const [statusData, summaryData, alertsData, trendsData, servicesData] = await Promise.all([
        apiGet<Parameters<typeof fromDashboardStatusResponse>[0]>('/api/system/dashboard/status'),
        apiGet<Parameters<typeof fromDashboardSummaryResponse>[0]>('/api/system/dashboard/summary'),
        apiGet<{ alerts: Parameters<typeof fromAlertRecord>[0][] }>('/api/system/dashboard/alerts?limit=10'),
        apiGet<Parameters<typeof fromTrendsResponse>[0]>(`/api/system/network-health/trends?hours=${trendHours}&buckets=24`),
        apiGet<ServiceListResponse>('/api/system/network-health/services?per_page=100'),
      ])

      setStatus(fromDashboardStatusResponse(statusData))
      setSummary(fromDashboardSummaryResponse(summaryData))
      setAlerts(alertsData.alerts.map(fromAlertRecord))
      setTrends(fromTrendsResponse(trendsData))

      const services = servicesData.items.map(fromServiceRecord)
      const problems = services
        .filter((s) => s.state !== 'OK')
        .sort((a, b) => SEVERITY_RANK[a.state] - SEVERITY_RANK[b.state])
        .slice(0, 6)
      setProblemServices(problems)

      setLastRefreshed(new Date())
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load dashboard data.'))
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trendHours])

  // Dashboard Refresh Rate (per-user, minutes). 0 = Manual: no auto-refresh.
  useEffect(() => {
    if (settings.dashboardRefreshRate <= 0) return

    const intervalMs = settings.dashboardRefreshRate * 60 * 1000
    const id = window.setInterval(() => {
      loadAll()
    }, intervalMs)

    return () => window.clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.dashboardRefreshRate])

  async function acknowledgeAlert(alert: AlertRow, comment: string) {
    try {
      await apiPost('/api/system/dashboard/alerts/acknowledge', {
        hostname: alert.hostname,
        service_name: alert.serviceName,
        comment,
      })
      setAckTarget(null)
      await loadAll()
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to acknowledge alert.'))
    }
  }

  const uptimeLabel = status?.nagios.running ? 'Online' : 'Offline'
  const uptimeColor = status?.nagios.running ? 'bg-emerald-500' : 'bg-red-500'
  const uptimeTextColor = status?.nagios.running ? 'text-emerald-600' : 'text-red-600'

  const downUnreachable = (summary?.hosts.down ?? 0) + (summary?.hosts.unreachable ?? 0)

  return (
    <main className="ml-[220px] flex-1 min-w-0">
      <div className="flex w-full min-w-0 gap-[var(--dash-grid-gap)]">
        <div className="min-w-0 flex-1 space-y-[var(--dash-section-gap)] py-6">

          {/* Sticky banner */}
          <div className="sticky top-0 z-10 bg-[var(--sticky-bg)] pb-3 pt-3">
            <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-[var(--dash-card-padding)] shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-semibold text-[var(--text)]">CICT Network</h2>
                  <p className="text-sm text-[var(--text-muted)]">
                    Last Updated: {formatDateTime(lastRefreshed, settings.dateTimeFormat, settings.timeZone)}
                  </p>
                  <p className="text-xs text-[var(--text-faint)]">
                    {settings.dashboardRefreshRate > 0
                      ? `Auto-refreshing every ${settings.dashboardRefreshRate} min`
                      : 'Auto-refresh: Manual'}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${uptimeColor}`} />
                    <span className={`text-sm ${uptimeTextColor}`}>{uptimeLabel}</span>
                  </div>
                  <RescanButton onScanComplete={() => loadAll()} />
                </div>
              </div>
            </div>
          </div>

          {loadError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
              {loadError}
            </div>
          )}

          <div className="grid gap-[var(--dash-grid-gap-sm)] sm:grid-cols-2 xl:grid-cols-4">
            <SummaryStatCard
              title="Total Hosts"
              value={String(summary?.hosts.total ?? 0)}
              subtitle={`${summary?.hosts.up ?? 0} online`}
              icon={Server}
              gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
            />
            <SummaryStatCard
              title="Network Latency"
              value={summary?.pingMetrics.avgRtaMs != null ? `${summary.pingMetrics.avgRtaMs} ms` : '—'}
              subtitle={summary?.pingMetrics.avgPacketLossPct != null ? `${summary.pingMetrics.avgPacketLossPct}% packet loss` : 'No data'}
              icon={Wifi}
              gradient="linear-gradient(135deg,#22C55E,#16A34A)"
            />
            <SummaryStatCard
              title="Active Warnings"
              value={String(summary?.activeAlerts.warning ?? 0)}
              subtitle="Needs attention"
              icon={AlertTriangle}
              gradient="linear-gradient(135deg,#EAB308,#CA8A04)"
            />
            <SummaryStatCard
              title="Critical Issues"
              value={String(summary?.activeAlerts.critical ?? 0)}
              subtitle={downUnreachable > 0 ? `${downUnreachable} hosts down` : 'Immediate action'}
              icon={Gauge}
              gradient="linear-gradient(135deg,#EF4444,#DC2626)"
            />
          </div>

          <div className="grid gap-[var(--dash-grid-gap)] lg:grid-cols-2">
            <NetworkStatusOverview
              up={summary?.hosts.up ?? 0}
              down={downUnreachable}
              isLoading={isLoading}
            />
            <NetworkPerformanceSection
              pingMetrics={summary?.pingMetrics ?? null}
              rtaTrend={trends?.ping.rta ?? []}
              isLoading={isLoading}
            />
          </div>

          {summary?.ncpaMetrics && (
            <ResourceUtilizationSection
              cpuTrend={trends?.ncpa?.cpu ?? []}
              isLoading={isLoading}
              hours={trendHours}
              onHoursChange={setTrendHours}
            />
          )}

          <RecentOutageTable
            alerts={alerts}
            isLoading={isLoading}
            onAcknowledge={(alert) => setAckTarget(alert)}
          />

        </div>

        <ServiceOverview
          status={status}
          summary={summary}
          problemServices={problemServices}
          isLoading={isLoading}
        />
      </div>

      {ackTarget && (
        <AcknowledgeModal
          alert={ackTarget}
          onCancel={() => setAckTarget(null)}
          onConfirm={(comment) => acknowledgeAlert(ackTarget, comment)}
        />
      )}
    </main>
  )
}

function AcknowledgeModal({
  alert,
  onCancel,
  onConfirm,
}: {
  alert: AlertRow
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
          Acknowledge {alert.hostname}{alert.serviceName ? ` / ${alert.serviceName}` : ''}
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
