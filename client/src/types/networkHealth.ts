// Mirrors server/app/api/system/network_health.py's summary endpoint.
// (trends/plugins are covered by types/dashboard.ts's TrendsResponse, which
// this page reuses.)
import { fromCountBlock, type CountBlock, type TrendPoint } from './dashboard'

export type NetworkHealthSummary = {
  hosts: CountBlock
  services: CountBlock
  activeAlerts: { total: number; critical: number; warning: number; unknown: number }
  // Last successful network discovery scan — shared by every user.
  lastScan: { completedAt: Date | null; isRunning: boolean }
}

type CountBlockRecord = Record<string, number>

type NetworkHealthSummaryApiResponse = {
  hosts: CountBlockRecord
  services: CountBlockRecord
  active_alerts: { total: number; critical: number; warning: number; unknown: number }
  last_scan?: { completed_at: string | null; is_running: boolean }
}

export function fromNetworkHealthSummaryResponse(
  data: NetworkHealthSummaryApiResponse
): NetworkHealthSummary {
  return {
    hosts: fromCountBlock(data.hosts),
    services: fromCountBlock(data.services),
    activeAlerts: data.active_alerts,
    lastScan: {
      completedAt: data.last_scan?.completed_at ? new Date(data.last_scan.completed_at) : null,
      isRunning: data.last_scan?.is_running ?? false,
    },
  }
}

// --- GET /network-health/availability ---------------------------------------

export type HostAvailability = {
  days: number
  availabilityPct: number | null
  // Latest day minus the day before, in percentage points.
  changePct: number | null
  // Latest day minus the first day with data, in percentage points.
  trendPct: number | null
  daily: { start: string; end: string; availabilityPct: number | null }[]
}

type HostAvailabilityApiResponse = {
  days: number
  availability_pct: number | null
  change_pct: number | null
  trend_pct: number | null
  daily: { start: string; end: string; availability_pct: number | null }[]
}

export function fromHostAvailabilityResponse(data: HostAvailabilityApiResponse): HostAvailability {
  return {
    days: data.days,
    availabilityPct: data.availability_pct,
    changePct: data.change_pct,
    trendPct: data.trend_pct,
    daily: data.daily.map((d) => ({ start: d.start, end: d.end, availabilityPct: d.availability_pct })),
  }
}

// --- GET /network-health/system-activity ------------------------------------

export type ServiceStateLabel = 'ok' | 'warning' | 'critical' | 'unknown'

export type SystemActivity = {
  processes: {
    deviceCount: number
    total: number
    avgPerDevice: number
    state: ServiceStateLabel
    peak24h: { hostname: string; count: number } | null
  } | null
  users: {
    deviceCount: number
    total: number
    minPerDevice: number
    maxPerDevice: number
    change1h: number | null
  } | null
}

type SystemActivityApiResponse = {
  processes: {
    device_count: number
    total: number
    avg_per_device: number
    state: ServiceStateLabel
    peak_24h: { hostname: string; count: number } | null
  } | null
  users: {
    device_count: number
    total: number
    min_per_device: number
    max_per_device: number
    change_1h: number | null
  } | null
}

export function fromSystemActivityResponse(data: SystemActivityApiResponse): SystemActivity {
  return {
    processes: data.processes
      ? {
          deviceCount: data.processes.device_count,
          total: data.processes.total,
          avgPerDevice: data.processes.avg_per_device,
          state: data.processes.state,
          peak24h: data.processes.peak_24h,
        }
      : null,
    users: data.users
      ? {
          deviceCount: data.users.device_count,
          total: data.users.total,
          minPerDevice: data.users.min_per_device,
          maxPerDevice: data.users.max_per_device,
          change1h: data.users.change_1h,
        }
      : null,
  }
}

// --- GET /network-health/cpu -------------------------------------------------

export type HostCpu = {
  hosts: string[]
  hostname: string | null
  service: string | null
  currentPct: number | null
  avgPct: number | null
  maxPct: number | null
  points: TrendPoint[]
}

type HostCpuApiResponse = {
  hosts: string[]
  hostname: string | null
  service: string | null
  current_pct: number | null
  avg_pct: number | null
  max_pct: number | null
  points: { bucket_start: string; avg_value: number | null; unit: string | null }[]
}

export function fromHostCpuResponse(data: HostCpuApiResponse): HostCpu {
  return {
    hosts: data.hosts,
    hostname: data.hostname,
    service: data.service,
    currentPct: data.current_pct,
    avgPct: data.avg_pct,
    maxPct: data.max_pct,
    points: data.points.map((p) => ({ bucketStart: p.bucket_start, avgValue: p.avg_value, unit: p.unit })),
  }
}

// --- GET /network-health/connections ----------------------------------------

export type ConnectionCounts = {
  available: boolean
  hostname: string
  established: number | null
  listening: number | null
  timeWait: number | null
  other: number | null
  total: number | null
}

type ConnectionCountsApiResponse = {
  available: boolean
  hostname: string
  established: number | null
  listening: number | null
  time_wait: number | null
  other: number | null
  total: number | null
}

export function fromConnectionsResponse(data: ConnectionCountsApiResponse): ConnectionCounts {
  return {
    available: data.available,
    hostname: data.hostname,
    established: data.established,
    listening: data.listening,
    timeWait: data.time_wait,
    other: data.other,
    total: data.total,
  }
}

// --- GET /network-health/insights -------------------------------------------

export type Insight = {
  severity: 'critical' | 'warning' | 'info' | 'ok'
  message: string
  at: Date | null
}

type InsightsApiResponse = {
  insights: { severity: Insight['severity']; message: string; at: string | null }[]
}

export function fromInsightsResponse(data: InsightsApiResponse): Insight[] {
  return data.insights.map((i) => ({ severity: i.severity, message: i.message, at: i.at ? new Date(i.at) : null }))
}

// --- GET /network-health/plugins --------------------------------------------

export type PluginGroup = {
  displayName: string
  total: number
  ok: number
  warning: number
  critical: number
  unknown: number
  worstState: 'ok' | 'warning' | 'critical' | 'unknown'
}

export type PluginsApiResponse = {
  groups: {
    display_name: string
    total: number
    ok: number
    warning: number
    critical: number
    unknown: number
    worst_state: PluginGroup['worstState']
  }[]
}

export function fromPluginsResponse(data: PluginsApiResponse): PluginGroup[] {
  return data.groups.map((g) => ({
    displayName: g.display_name,
    total: g.total,
    ok: g.ok,
    warning: g.warning,
    critical: g.critical,
    unknown: g.unknown,
    worstState: g.worst_state,
  }))
}

// --- GET /network-health/plugin-trends --------------------------------------

export type PluginMetric = {
  metric: string
  unit: string | null
  // True for durations and percentages, which are averaged across services;
  // sizes and counts only have per-service values.
  averaged: boolean
  serviceCount: number
  currentAvg: number | null
  current: { hostname: string; service: string; value: number }[]
  points: TrendPoint[]
}

export type AddedPlugin = {
  pluginName: string
  displayName: string
  total: number
  ok: number
  warning: number
  critical: number
  unknown: number
  worstState: 'ok' | 'warning' | 'critical' | 'unknown'
  metrics: PluginMetric[]
}

type PluginTrendsApiResponse = {
  hours: number
  plugins: {
    plugin_name: string
    display_name: string
    total: number
    ok: number
    warning: number
    critical: number
    unknown: number
    worst_state: AddedPlugin['worstState']
    metrics: {
      metric: string
      unit: string | null
      averaged: boolean
      service_count: number
      current_avg: number | null
      current: { hostname: string; service: string; value: number }[]
      points: { bucket_start: string; avg_value: number | null; unit: string | null }[]
    }[]
  }[]
}

export function fromPluginTrendsResponse(data: PluginTrendsApiResponse): AddedPlugin[] {
  return data.plugins.map((p) => ({
    pluginName: p.plugin_name,
    displayName: p.display_name,
    total: p.total,
    ok: p.ok,
    warning: p.warning,
    critical: p.critical,
    unknown: p.unknown,
    worstState: p.worst_state,
    metrics: p.metrics.map((m) => ({
      metric: m.metric,
      unit: m.unit,
      averaged: m.averaged,
      serviceCount: m.service_count,
      currentAvg: m.current_avg,
      current: m.current,
      points: m.points.map((pt) => ({ bucketStart: pt.bucket_start, avgValue: pt.avg_value, unit: pt.unit })),
    })),
  }))
}
