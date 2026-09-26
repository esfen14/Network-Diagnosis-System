// Mirrors the report endpoints exposed by server/app/api/system/report.py.

export type ReportPeriod = 'last_24h' | 'today' | 'last_7d' | 'last_30d' | 'last_90d' | 'custom'

export type PeriodMeta = {
  period: string
  start: string
  end: string
}

// --- GET /report/availability -----------------------------------------

export type HostAvailabilityRow = {
  hostname: string
  state: string
  uptimePct: number | null
  totalSnapshots: number
  lastCheck: string | null
  lastStateChange: string | null
}

export type HostAvailabilityReport = {
  period: PeriodMeta
  summary: {
    total: number
    up: number
    down: number
    unreachable: number
    uptimePct: number | null
  }
  hosts: HostAvailabilityRow[]
}

type HostAvailabilityApiRecord = {
  hostname: string
  state: string
  uptime_pct: number | null
  total_snapshots: number
  last_check: string | null
  last_state_change: string | null
}

type HostAvailabilityApiResponse = {
  period: PeriodMeta
  summary: {
    total: number
    up: number
    down: number
    unreachable: number
    uptime_pct: number | null
  }
  hosts: HostAvailabilityApiRecord[]
}

export function fromHostAvailabilityResponse(data: HostAvailabilityApiResponse): HostAvailabilityReport {
  return {
    period: data.period,
    summary: {
      total: data.summary.total,
      up: data.summary.up,
      down: data.summary.down,
      unreachable: data.summary.unreachable,
      uptimePct: data.summary.uptime_pct,
    },
    hosts: data.hosts.map((h) => ({
      hostname: h.hostname,
      state: h.state,
      uptimePct: h.uptime_pct,
      totalSnapshots: h.total_snapshots,
      lastCheck: h.last_check,
      lastStateChange: h.last_state_change,
    })),
  }
}

// --- GET /report/network-services ---------------------------------------

export type ServiceRow = {
  service: string
  totalInstances: number
  ok: number
  warning: number
  critical: number
  unknown: number
  uptimePct: number | null
}

export type NetworkServicesReport = {
  period: PeriodMeta
  summary: {
    totalServices: number
    totalInstances: number
    ok: number
    warning: number
    critical: number
    unknown: number
    uptimePct: number | null
  }
  services: ServiceRow[]
}

type ServiceApiRecord = {
  service: string
  total_instances: number
  ok: number
  warning: number
  critical: number
  unknown: number
  uptime_pct: number | null
}

type NetworkServicesApiResponse = {
  period: PeriodMeta
  summary: {
    total_services: number
    total_instances: number
    ok: number
    warning: number
    critical: number
    unknown: number
    uptime_pct: number | null
  }
  services: ServiceApiRecord[]
}

export function fromNetworkServicesResponse(data: NetworkServicesApiResponse): NetworkServicesReport {
  return {
    period: data.period,
    summary: {
      totalServices: data.summary.total_services,
      totalInstances: data.summary.total_instances,
      ok: data.summary.ok,
      warning: data.summary.warning,
      critical: data.summary.critical,
      unknown: data.summary.unknown,
      uptimePct: data.summary.uptime_pct,
    },
    services: data.services.map((s) => ({
      service: s.service,
      totalInstances: s.total_instances,
      ok: s.ok,
      warning: s.warning,
      critical: s.critical,
      unknown: s.unknown,
      uptimePct: s.uptime_pct,
    })),
  }
}
