import { useCallback, useEffect, useState } from 'react'
import { MonitorOff, MonitorSmartphone, RefreshCw, Timer, WifiOff } from 'lucide-react'
import { ActiveConnectionsCard } from '../components/network-health/ActiveConnectionsCard'
import { CpuLoadChart } from '../components/network-health/CpuLoadChart'
import { CpuUtilizationChart } from '../components/network-health/CpuUtilizationChart'
import { DeviceCountCard } from '../components/network-health/DeviceCountCard'
import { HostAvailabilityCard } from '../components/network-health/HostAvailabilityCard'
import { InsightsPanel } from '../components/network-health/InsightsPanel'
import { MetricGraphModal, type GraphSeriesConfig, type TrendHours } from '../components/network-health/MetricGraphModal'
import { NetworkInfoCard } from '../components/network-health/NetworkInfoCard'
import { ResourceUsageCard } from '../components/network-health/ResourceUsageCard'
import { SparklineMetricCard } from '../components/network-health/SparklineMetricCard'
import { SystemActivityCard } from '../components/network-health/SystemActivityCard'
import { TrendStatCard } from '../components/network-health/TrendStatCard'
import { PageHeader } from '../components/shared/PageHeader'
import { RescanModal } from '../components/shared/RescanModal'
import { useCurrentUser } from '../contexts/CurrentUserContext'
import { useSystemSettings } from '../contexts/SystemSettingsContext'
import { useNetworkRescan } from '../hooks/useNetworkRescan'
import { apiGet, errorMessage } from '../lib/api'
import { fromTrendsResponse, type TrendPoint, type TrendsResponse } from '../types/dashboard'
import { fromNetworkHealthSummaryResponse, type NetworkHealthSummary } from '../types/networkHealth'
import { formatDate, formatTime, formatTimeAgo } from '../utils/formatDateTime'

type MetricKey = 'latency' | 'bandwidth' | 'packetLoss' | 'avgResponseTime' | 'avgResource'

type MetricConfig = {
  title: string
  unit: string
  datasourceLabel: string
  series: GraphSeriesConfig[]
  seriesData: Record<string, TrendPoint[]>
  isConfigured: boolean
  emptyMessage?: string
}

/** Latest non-null bucket value, plus % change from the first non-null bucket. */
function latestAndChange(trend: TrendPoint[] | undefined): { latest: number | null; changePct: number | null } {
  const values = (trend ?? []).filter((p) => p.avgValue != null) as { avgValue: number }[]
  if (values.length === 0) return { latest: null, changePct: null }
  const latest = values[values.length - 1].avgValue
  const first = values[0].avgValue
  if (values.length < 2 || first === 0) return { latest, changePct: null }
  return { latest, changePct: ((latest - first) / first) * 100 }
}

function changeLabel(changePct: number | null): { text: string; type: 'positive' | 'negative' | 'neutral' } {
  if (changePct == null) return { text: 'No data', type: 'neutral' }
  const rounded = changePct.toFixed(1)
  return changePct <= 0
    ? { text: `${rounded}%`, type: 'positive' }
    : { text: `+${rounded}%`, type: 'negative' }
}

// How often to re-check while a scan (possibly started by someone else) runs.
const RUNNING_SCAN_POLL_MS = 15_000

export function NetworkHealthPage() {
  const [openMetric, setOpenMetric] = useState<MetricKey | null>(null)

  const [trendHours, setTrendHours] = useState<TrendHours>(24)
  const [summary, setSummary] = useState<NetworkHealthSummary | null>(null)
  const [trends, setTrends] = useState<TrendsResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setLoadError(null)
    try {
      const [summaryData, trendsData] = await Promise.all([
        apiGet<Parameters<typeof fromNetworkHealthSummaryResponse>[0]>('/api/system/network-health/summary'),
        apiGet<Parameters<typeof fromTrendsResponse>[0]>(`/api/system/network-health/trends?hours=${trendHours}&buckets=24`),
      ])
      setSummary(fromNetworkHealthSummaryResponse(summaryData))
      setTrends(fromTrendsResponse(trendsData))
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load network health data.'))
    } finally {
      setIsLoading(false)
    }
  }, [trendHours])

  useEffect(() => {
    loadData()
  }, [loadData])

  // "Last Scan" comes from the server (the latest successful network
  // discovery), so every user sees the same time. Running a scan needs the
  // discover permission; everyone else just sees the time.
  const { hasPermission } = useCurrentUser()
  const canRescan = hasPermission('system.discover')
  const rescan = useNetworkRescan(loadData)
  const { savedSettings } = useSystemSettings()

  // Keeps "5 min ago" current while the page stays open.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000)
    return () => window.clearInterval(id)
  }, [])

  // While a scan runs (including one another user started), re-check the
  // summary so the time updates when it finishes.
  const scanRunning = summary?.lastScan.isRunning ?? false
  useEffect(() => {
    if (!scanRunning) return
    const id = window.setInterval(() => {
      apiGet<Parameters<typeof fromNetworkHealthSummaryResponse>[0]>('/api/system/network-health/summary')
        .then((data) => setSummary(fromNetworkHealthSummaryResponse(data)))
        .catch(() => {
          // Non-fatal — try again next interval.
        })
    }, RUNNING_SCAN_POLL_MS)
    return () => window.clearInterval(id)
  }, [scanRunning])

  const lastScanAt = summary?.lastScan.completedAt ?? null
  const isScanning = scanRunning || rescan.state === 'scanning'
  const lastScanText = isScanning
    ? 'Scanning…'
    : lastScanAt ? formatTimeAgo(lastScanAt, now) : summary ? 'Never' : '—'
  const lastScanDate = lastScanAt ? formatDate(lastScanAt, savedSettings.dateTimeFormat, savedSettings.timeZone) : 'Never'
  const lastScanTime = lastScanAt ? formatTime(lastScanAt, savedSettings.timeZone) : '—'

  const rta = latestAndChange(trends?.ping.rta)
  const packetLoss = latestAndChange(trends?.ping.packetLoss)
  const cpu = latestAndChange(trends?.ncpa?.cpu)
  const memory = latestAndChange(trends?.ncpa?.memory)
  const disk = latestAndChange(trends?.ncpa?.disk)

  const rtaChange = changeLabel(rta.changePct)
  const plChange = changeLabel(packetLoss.changePct)

  const METRIC_MODALS: Record<MetricKey, MetricConfig> = {
    latency: {
      title: 'Latency',
      unit: 'ms',
      datasourceLabel: 'Ping RTA — network-wide average',
      series: [{ key: 'rta', label: 'Round-trip Latency', color: '#10B981' }],
      seriesData: { rta: trends?.ping.rta ?? [] },
      isConfigured: trends?.ping.configured ?? false,
      emptyMessage: 'No ping checks are configured on any monitored host yet.',
    },
    packetLoss: {
      title: 'Packets Loss',
      unit: '%',
      datasourceLabel: 'Ping packet loss — network-wide average',
      series: [{ key: 'pl', label: 'Packet Loss', color: '#EF4444', precision: 2 }],
      seriesData: { pl: trends?.ping.packetLoss ?? [] },
      isConfigured: trends?.ping.configured ?? false,
      emptyMessage: 'No ping checks are configured on any monitored host yet.',
    },
    avgResource: {
      title: 'Average Resource',
      unit: '%',
      datasourceLabel: 'NCPA agents — network-wide average',
      series: [
        { key: 'cpu', label: 'CPU Usage', color: '#F4A90B' },
        { key: 'memory', label: 'Memory Usage', color: '#38BDF8' },
        { key: 'disk', label: 'Disk Usage', color: '#22C55E' },
      ],
      seriesData: {
        cpu: trends?.ncpa?.cpu ?? [],
        memory: trends?.ncpa?.memory ?? [],
        disk: trends?.ncpa?.disk ?? [],
      },
      isConfigured: trends?.ncpa != null,
      emptyMessage: 'No NCPA agents are deployed on any monitored host yet.',
    },
    bandwidth: {
      title: 'Bandwidth',
      unit: 'Mbps',
      datasourceLabel: 'Interface throughput',
      series: [{ key: 'bandwidth', label: 'Throughput', color: '#38BDF8' }],
      seriesData: { bandwidth: [] },
      isConfigured: false,
      emptyMessage: 'No bandwidth/throughput plugin is wired into monitoring yet.',
    },
    avgResponseTime: {
      title: 'Avg. Response Time',
      unit: 'ms',
      datasourceLabel: 'Service response time',
      series: [{ key: 'response', label: 'Response Time', color: '#A78BFA' }],
      seriesData: { response: [] },
      isConfigured: false,
      emptyMessage: 'No dedicated response-time metric is exposed yet — see Latency for ping RTA.',
    },
  }

  return (
    <main className="ml-[220px] flex-1 min-w-0">
      <div className="min-w-0 py-6">
        {/* Sticky header row */}
        <div className="sticky top-0 z-10 bg-[var(--sticky-bg)] pb-3 pt-3">
          <div className="flex flex-wrap items-start gap-4 sm:gap-8">
            <div className="min-w-0 flex-1">
              <PageHeader
                title="Network Health"
                description="Overview of system performance."
              />
            </div>

            <div className="flex w-full shrink-0 justify-center pt-2 sm:w-72">
              <button
                type="button"
                onClick={rescan.open}
                disabled={!canRescan || isScanning}
                title={canRescan ? undefined : "Your role can't run network scans"}
                className="flex items-center gap-2 rounded-3xl bg-[#F4A90B] px-4 py-2 text-sm font-medium text-white shadow-md transition hover:opacity-90 active:scale-[0.99] cursor-pointer disabled:cursor-default disabled:hover:opacity-100 disabled:active:scale-100"
              >
                <RefreshCw className={`h-4 w-4 ${isScanning ? 'animate-spin' : ''}`} />
                Last Scan: {lastScanText}
              </button>
            </div>
          </div>
        </div>

        {loadError && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
            {loadError}
          </div>
        )}

        <div className="mt-6 flex flex-col gap-6 lg:flex-row lg:items-start lg:gap-8">
          <div className="min-w-0 flex-1 space-y-6">
            <div className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-12">
              <div className="flex flex-col gap-4 lg:col-span-5">
                <NetworkInfoCard
                  lastScanTime={lastScanTime}
                  lastScanDate={lastScanDate}
                  onStartScan={canRescan && !isScanning ? rescan.open : undefined}
                />
                <div className="flex-1">
                  <ResourceUsageCard
                    cpuPct={cpu.latest}
                    memoryPct={memory.latest}
                    diskPct={disk.latest}
                    onClick={() => setOpenMetric('avgResource')}
                  />
                </div>
              </div>

              <div className="flex flex-col gap-4 lg:col-span-7">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <DeviceCountCard
                    title="Online Devices"
                    count={summary?.hosts.up ?? 0}
                    icon={MonitorSmartphone}
                    iconBg="bg-emerald-500"
                  />

                  <DeviceCountCard
                    title="Offline Devices"
                    count={(summary?.hosts.down ?? 0) + (summary?.hosts.unreachable ?? 0)}
                    icon={MonitorOff}
                    iconBg="bg-red-700"
                  />
                </div>

                <HostAvailabilityCard />
                <SystemActivityCard />
              </div>
            </div>

            <div className="space-y-4">
              <CpuUtilizationChart />
              <CpuLoadChart />
            </div>
          </div>

          <div className="flex w-full shrink-0 flex-col gap-4 lg:w-72">
            <div className="space-y-4 border-t border-[var(--border)] pt-6 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
              <SparklineMetricCard
                title="Latency"
                value={rta.latest != null ? rta.latest.toFixed(1) : '—'}
                unit="ms"
                change={rtaChange.text}
                changeType={rtaChange.type}
                sparklineData={(trends?.ping.rta ?? []).map((p) => p.avgValue ?? 0)}
                sparklineColor="#10B981"
                onClick={() => setOpenMetric('latency')}
              />

              <TrendStatCard
                title="Packets Loss"
                value={packetLoss.latest != null ? `${packetLoss.latest.toFixed(2)}%` : '—'}
                change={plChange.text}
                changeType={plChange.type}
                icon={WifiOff}
                onClick={() => setOpenMetric('packetLoss')}
              />

              <SparklineMetricCard
                title="Bandwidth"
                value="—"
                unit=""
                change="Not configured"
                changeType="neutral"
                sparklineData={[]}
                sparklineColor="#E70D0D"
                onClick={() => setOpenMetric('bandwidth')}
              />

              <TrendStatCard
                title="Avg. Response Time"
                value="—"
                change="Not configured"
                changeType="neutral"
                icon={Timer}
                onClick={() => setOpenMetric('avgResponseTime')}
              />

              <ActiveConnectionsCard />
            </div>

            <InsightsPanel />
          </div>
        </div>
      </div>

      <RescanModal
        state={rescan.state}
        progress={rescan.progress}
        errorText={rescan.errorText}
        onConfirm={rescan.confirm}
        onClose={rescan.close}
      />

      {openMetric && (
        <MetricGraphModal
          {...METRIC_MODALS[openMetric]}
          hours={trendHours}
          onHoursChange={setTrendHours}
          isLoading={isLoading}
          onClose={() => setOpenMetric(null)}
        />
      )}
    </main>
  )
}
