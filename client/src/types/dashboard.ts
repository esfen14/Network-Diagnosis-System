// Mirrors server/app/api/system/dashboard.py and network_health.py's
// summary/status/alerts/trends endpoints.

export type CountBlock = {
  total: number
  up?: number
  down?: number
  unreachable?: number
  ok?: number
  warning?: number
  critical?: number
  unknown?: number
  flapping?: number
  inDowntime?: number
}

export type PingMetrics = {
  configured: boolean
  avgRtaMs: number | null
  avgPacketLossPct: number | null
  hostCount: number
  insufficientData?: boolean
}

export type NcpaMetrics = {
  ncpaHostCount: number
  totalHostCount: number
  avgCpuPct: number | null
  avgDiskPct: number | null
  avgMemoryPct: number | null
} | null

export type DashboardSummary = {
  hosts: CountBlock
  services: CountBlock
  activeAlerts: { total: number; critical: number; warning: number; unknown: number }
  pingMetrics: PingMetrics
  ncpaMetrics: NcpaMetrics
}

type CountBlockRecord = Record<string, number>

function fromCountBlock(r: CountBlockRecord): CountBlock {
  return {
    total: r.total,
    up: r.up,
    down: r.down,
    unreachable: r.unreachable,
    ok: r.ok,
    warning: r.warning,
    critical: r.critical,
    unknown: r.unknown,
    flapping: r.flapping,
    inDowntime: r.in_downtime,
  }
}

type DashboardSummaryApiResponse = {
  hosts: CountBlockRecord
  services: CountBlockRecord
  active_alerts: { total: number; critical: number; warning: number; unknown: number }
  ping_metrics: {
    configured: boolean
    avg_rta_ms: number | null
    avg_packet_loss_pct: number | null
    host_count: number
    insufficient_data?: boolean
  }
  ncpa_metrics: {
    ncpa_host_count: number
    total_host_count: number
    avg_cpu_pct: number | null
    avg_disk_pct: number | null
    avg_memory_pct: number | null
  } | null
}

export function fromDashboardSummaryResponse(data: DashboardSummaryApiResponse): DashboardSummary {
  return {
    hosts: fromCountBlock(data.hosts),
    services: fromCountBlock(data.services),
    activeAlerts: data.active_alerts,
    pingMetrics: {
      configured: data.ping_metrics.configured,
      avgRtaMs: data.ping_metrics.avg_rta_ms,
      avgPacketLossPct: data.ping_metrics.avg_packet_loss_pct,
      hostCount: data.ping_metrics.host_count,
      insufficientData: data.ping_metrics.insufficient_data,
    },
    ncpaMetrics: data.ncpa_metrics
      ? {
          ncpaHostCount: data.ncpa_metrics.ncpa_host_count,
          totalHostCount: data.ncpa_metrics.total_host_count,
          avgCpuPct: data.ncpa_metrics.avg_cpu_pct,
          avgDiskPct: data.ncpa_metrics.avg_disk_pct,
          avgMemoryPct: data.ncpa_metrics.avg_memory_pct,
        }
      : null,
  }
}

// --- GET /dashboard/status -----------------------------------------------

export type DashboardStatus = {
  nagios: {
    running: boolean
    version: string | null
    lastStatusUpdate: string | null
    activeHostChecks: boolean | null
    activeServiceChecks: boolean | null
  }
}

type DashboardStatusApiResponse = {
  nagios: {
    running: boolean
    version: string | null
    last_status_update: string | null
    active_host_checks: boolean | null
    active_service_checks: boolean | null
  }
}

export function fromDashboardStatusResponse(data: DashboardStatusApiResponse): DashboardStatus {
  return {
    nagios: {
      running: data.nagios.running,
      version: data.nagios.version,
      lastStatusUpdate: data.nagios.last_status_update,
      activeHostChecks: data.nagios.active_host_checks,
      activeServiceChecks: data.nagios.active_service_checks,
    },
  }
}

// --- GET /dashboard/alerts -------------------------------------------------

export type AlertRow = {
  type: 'host' | 'service'
  hostname: string
  serviceName: string | null
  state: string
  stateType: string
  timestamp: number
  durationSeconds: number
  pluginOutput: string
  inDowntime: boolean
  ack: { comment: string; acknowledgedBy: string; acknowledgedAt: string } | null
}

type AlertApiRecord = {
  type: 'host' | 'service'
  hostname: string
  service_name: string | null
  state: string
  state_type: string
  timestamp: number
  duration_seconds: number
  plugin_output: string
  in_downtime: boolean
  ack: { comment: string; acknowledged_by: string; acknowledged_at: string } | null
}

export function fromAlertRecord(record: AlertApiRecord): AlertRow {
  return {
    type: record.type,
    hostname: record.hostname,
    serviceName: record.service_name,
    state: record.state,
    stateType: record.state_type,
    timestamp: record.timestamp,
    durationSeconds: record.duration_seconds,
    pluginOutput: record.plugin_output,
    inDowntime: record.in_downtime,
    ack: record.ack
      ? {
          comment: record.ack.comment,
          acknowledgedBy: record.ack.acknowledged_by,
          acknowledgedAt: record.ack.acknowledged_at,
        }
      : null,
  }
}

// --- GET /network-health/trends -------------------------------------------

export type TrendPoint = { bucketStart: string; avgValue: number | null; unit: string | null }

type TrendPointRecord = { bucket_start: string; avg_value: number | null; unit: string | null }

function fromTrendPoints(records: TrendPointRecord[]): TrendPoint[] {
  return records.map((r) => ({ bucketStart: r.bucket_start, avgValue: r.avg_value, unit: r.unit }))
}

export type TrendsResponse = {
  ping: { configured: boolean; rta: TrendPoint[]; packetLoss: TrendPoint[] }
  ncpa: { cpu: TrendPoint[]; disk: TrendPoint[]; memory: TrendPoint[] } | null
}

type TrendsApiResponse = {
  ping: { configured: boolean; rta: TrendPointRecord[]; packet_loss: TrendPointRecord[] }
  ncpa: { cpu: TrendPointRecord[]; disk: TrendPointRecord[]; memory: TrendPointRecord[] } | null
}

export function fromTrendsResponse(data: TrendsApiResponse): TrendsResponse {
  return {
    ping: {
      configured: data.ping.configured,
      rta: fromTrendPoints(data.ping.rta),
      packetLoss: fromTrendPoints(data.ping.packet_loss),
    },
    ncpa: data.ncpa
      ? {
          cpu: fromTrendPoints(data.ncpa.cpu),
          disk: fromTrendPoints(data.ncpa.disk),
          memory: fromTrendPoints(data.ncpa.memory),
        }
      : null,
  }
}
