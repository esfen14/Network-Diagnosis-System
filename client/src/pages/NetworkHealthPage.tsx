import { useCallback, useEffect, useState } from 'react'
import { MonitorOff, MonitorSmartphone, RefreshCw, Timer, WifiOff } from 'lucide-react'
import { ActiveConnectionsCard } from '../components/network-health/ActiveConnectionsCard'
import { AddedPluginsSection } from '../components/network-health/AddedPluginsSection'
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
import { useCurrentUser } from '../contexts/CurrentUserContext'
import { useSystemSettings } from '../contexts/SystemSettingsContext'
import { useNetworkProfile } from '../hooks/useNetworkProfile'
import { useNetworkRescan } from '../hooks/useNetworkRescan'
import { apiGet, errorMessage } from '../lib/api'
import { fromTrendsResponse, type TrendPoint, type TrendsResponse } from '../types/dashboard'
import {
  fromConnectionsResponse,
  fromHostAvailabilityResponse,
  fromHostCpuResponse,
  fromInsightsResponse,
  fromNetworkHealthSummaryResponse,
  fromPluginTrendsResponse,
  fromPluginsResponse,
  fromSystemActivityResponse,
  type ConnectionCounts,
  type HostAvailability,
  type HostCpu,
  type AddedPlugin,
  type Insight,
  type NetworkHealthSummary,
  type PluginsApiResponse,
  type SystemActivity,
} from '../types/networkHealth'
import { formatDate, formatTime, formatTimeAgo } from '../utils/formatDateTime'
import { trendBuckets } from '../utils/trendHours'

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

// One independently loaded card: its data, or why it could not load.
type Widget<T> = { data: T | null; error: string | null }

const EMPTY_WIDGET = { data: null, error: null }

/** Store one widget's result (or its error) as soon as its request settles. */
function loadWidget<T>(request: Promise<T>, setWidget: (widget: Widget<T>) => void, fallback: string) {
  request
    .then((data) => setWidget({ data, error: null }))
    .catch((err) => setWidget({ data: null, error: errorMessage(err, fallback) }))
}

// How often to re-check while a scan (possibly started by someone else) runs.
const RUNNING_SCAN_POLL_MS = 15_000

export function NetworkHealthPage() {
  const [openMetric, setOpenMetric] = useState<MetricKey | null>(null)

  const [trendHours, setTrendHours] = useState<TrendHours>(24)
  const [cpuHours, setCpuHours] = useState<TrendHours>(24)
  const [loadHours, setLoadHours] = useState<TrendHours>(24)
  const [cpuLoad, setCpuLoad] = useState<TrendsResponse['nagiosCpuLoad'] | null>(null)
  const [isLoadLoading, setIsLoadLoading] = useState(true)
  const [summary, setSummary] = useState<NetworkHealthSummary | null>(null)
  const [trends, setTrends] = useState<TrendsResponse | null>(null)
  const [supportedChecks, setSupportedChecks] = useState<string[] | null>(null)
  const [availability, setAvailability] = useState<Widget<HostAvailability>>(EMPTY_WIDGET)
  const [activity, setActivity] = useState<Widget<SystemActivity>>(EMPTY_WIDGET)
  const [connections, setConnections] = useState<Widget<ConnectionCounts>>(EMPTY_WIDGET)
  const [insights, setInsights] = useState<Widget<Insight[]>>(EMPTY_WIDGET)
  const [addedPlugins, setAddedPlugins] = useState<Widget<AddedPlugin[]>>(EMPTY_WIDGET)
  const [hostCpu, setHostCpu] = useState<Widget<HostCpu>>(EMPTY_WIDGET)
  // null = let the server pick (the Nagios server, else the first NCPA host).
  const [cpuHost, setCpuHost] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setIsLoading(true)
    setLoadError(null)

    // Cards that each have their own backend load independently: one slow
    // or failing request (e.g. availability waiting on Nagios' archive CGI)
    // must not hold back or blank the others.
    loadWidget(
      apiGet<Parameters<typeof fromHostAvailabilityResponse>[0]>('/api/system/network-health/availability?days=7')
        .then(fromHostAvailabilityResponse),
      setAvailability,
      'Unable to load availability from Nagios.',
    )
    loadWidget(
      apiGet<Parameters<typeof fromSystemActivityResponse>[0]>('/api/system/network-health/system-activity')
        .then(fromSystemActivityResponse),
      setActivity,
      'Unable to load system activity.',
    )
    loadWidget(
      apiGet<Parameters<typeof fromConnectionsResponse>[0]>('/api/system/network-health/connections')
        .then(fromConnectionsResponse),
      setConnections,
      'Unable to load connections.',
    )
    loadWidget(
      apiGet<Parameters<typeof fromInsightsResponse>[0]>('/api/system/network-health/insights')
        .then(fromInsightsResponse),
      setInsights,
      'Unable to load insights.',
    )
    loadWidget(
      apiGet<Parameters<typeof fromPluginTrendsResponse>[0]>(`/api/system/network-health/plugin-trends?hours=${trendHours}&buckets=${trendBuckets(trendHours)}`)
        .then(fromPluginTrendsResponse),
      setAddedPlugins,
      'Unable to load added plugins.',
    )

    try {
      const [summaryData, trendsData, pluginsData] = await Promise.all([
        apiGet<Parameters<typeof fromNetworkHealthSummaryResponse>[0]>('/api/system/network-health/summary'),
        apiGet<Parameters<typeof fromTrendsResponse>[0]>(`/api/system/network-health/trends?hours=${trendHours}&buckets=${trendBuckets(trendHours)}`),
        apiGet<PluginsApiResponse | null>('/api/system/network-health/plugins'),
      ])
      setSummary(fromNetworkHealthSummaryResponse(summaryData))
      setTrends(fromTrendsResponse(trendsData))
      setSupportedChecks(pluginsData ? fromPluginsResponse(pluginsData).map((g) => g.displayName) : [])
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load network health data.'))
    } finally {
      setIsLoading(false)
    }
  }, [trendHours])

  useEffect(() => {
    loadData()
  }, [loadData])

  useEffect(() => {
    let cancelled = false
    const params = new URLSearchParams({ hours: String(cpuHours), buckets: String(trendBuckets(cpuHours)) })
    if (cpuHost) params.set('hostname', cpuHost)
    apiGet<Parameters<typeof fromHostCpuResponse>[0]>(`/api/system/network-health/cpu?${params}`)
      .then((data) => {
        if (!cancelled) setHostCpu({ data: fromHostCpuResponse(data), error: null })
      })
      .catch((err) => {
        if (!cancelled) setHostCpu({ data: null, error: errorMessage(err, 'Unable to load CPU utilization.') })
      })
    return () => {
      cancelled = true
    }
  }, [cpuHours, cpuHost])

  useEffect(() => {
    let cancelled = false
    setIsLoadLoading(true)
    apiGet<Parameters<typeof fromTrendsResponse>[0]>(`/api/system/network-health/trends?hours=${loadHours}&buckets=${trendBuckets(loadHours)}`)
      .then((data) => {
        if (!cancelled) setCpuLoad(fromTrendsResponse(data).nagiosCpuLoad)
      })
      .catch(() => {
        if (!cancelled) setCpuLoad(null)
      })
      .finally(() => {
        if (!cancelled) setIsLoadLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [loadHours])

  // "Last Scan" comes from the server (the latest successful network
  // discovery), so every user sees the same time. Running a scan needs the
  // discover permission; everyone else just sees the time.
  const { hasPermission } = useCurrentUser()
  const canRescan = hasPermission('system.discover')
  const rescan = useNetworkRescan(loadData)
  const canEditProfile = hasPermission('settings.discovery')
  const networkProfile = useNetworkProfile()
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
  const startScan = canRescan && !isScanning ? rescan.start : undefined
  const lastScanText = isScanning
    ? 'Scanning…'
    : lastScanAt ? formatTimeAgo(lastScanAt, now) : summary ? 'No scan recorded' : '—'
  const lastScanDate = lastScanAt ? formatDate(lastScanAt, savedSettings.dateTimeFormat, savedSettings.timeZone) : 'No scan recorded'
  const lastScanTime = lastScanAt ? formatTime(lastScanAt, savedSettings.timeZone) : '—'

  const rta = latestAndChange(trends?.ping.rta)
  const packetLoss = latestAndChange(trends?.ping.packetLoss)
  const cpu = latestAndChange(trends?.ncpa?.cpu)
  const memory = latestAndChange(trends?.ncpa?.memory)
  const disk = latestAndChange(trends?.ncpa?.disk)

  const bandwidthIn = latestAndChange(trends?.bandwidth.in)
  const bandwidthOut = latestAndChange(trends?.bandwidth.out)
  const bandwidthTotal = (trends?.bandwidth.in ?? []).map(
    (p, i) => (p.avgValue ?? 0) + (trends?.bandwidth.out[i]?.avgValue ?? 0),
  )
  const bandwidthLatest =
    bandwidthIn.latest != null || bandwidthOut.latest != null
      ? (bandwidthIn.latest ?? 0) + (bandwidthOut.latest ?? 0)
      : null
  const bandwidthChange = changeLabel(
    bandwidthLatest == null ? null : latestAndChange(bandwidthTotal.map((v) => ({ bucketStart: '', avgValue: v, unit: null }))).changePct,
  )

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
      datasourceLabel: 'NCPA interface throughput — summed across monitored interfaces',
      series: [
        { key: 'in', label: 'Inbound', color: '#38BDF8', precision: 2 },
        { key: 'out', label: 'Outbound', color: '#F4A90B', precision: 2 },
      ],
      seriesData: { in: trends?.bandwidth.in ?? [], out: trends?.bandwidth.out ?? [] },
      isConfigured: trends?.bandwidth.configured ?? false,
      emptyMessage: 'Plugin not configured — add NCPA interface/<name>/bytes_recv and bytes_sent metrics (checked with delta) in Settings → Plugins to see bandwidth.',
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
                onClick={startScan}
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

        {rescan.errorText && (
          <div role="alert" className="mt-4 flex items-start justify-between gap-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
            <span>Network rescan failed: {rescan.errorText}</span>
            <button type="button" onClick={rescan.dismissError} className="shrink-0 font-medium underline">
              Dismiss
            </button>
          </div>
        )}

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
                  profile={networkProfile.profile}
                  onSave={canEditProfile ? networkProfile.save : undefined}
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

                <HostAvailabilityCard data={availability.data} error={availability.error} />
                <SystemActivityCard data={activity.data} error={activity.error} />
              </div>
            </div>

            <div className="space-y-4">
              <CpuUtilizationChart
                data={hostCpu.data}
                error={hostCpu.error}
                hours={cpuHours}
                onHoursChange={setCpuHours}
                onHostChange={setCpuHost}
              />
              <CpuLoadChart
                load={cpuLoad ?? { configured: false, load1: [], load5: [], load15: [] }}
                hours={loadHours}
                onHoursChange={setLoadHours}
                isLoading={isLoadLoading}
              />
              <AddedPluginsSection
                plugins={addedPlugins.data}
                error={addedPlugins.error}
                hours={trendHours}
                onHoursChange={setTrendHours}
                isLoading={isLoading}
              />
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
                value={bandwidthLatest != null ? bandwidthLatest.toFixed(2) : '—'}
                unit={bandwidthLatest != null ? 'Mbps' : ''}
                change={trends?.bandwidth.configured ? bandwidthChange.text : 'Not configured'}
                changeType={trends?.bandwidth.configured ? bandwidthChange.type : 'neutral'}
                sparklineData={bandwidthTotal}
                sparklineColor="#38BDF8"
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

              <ActiveConnectionsCard data={connections.data} error={connections.error} />
            </div>

            <InsightsPanel
              insights={insights.data}
              insightsError={insights.error}
              supportedChecks={supportedChecks}
              now={now}
            />
          </div>
        </div>
      </div>

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
