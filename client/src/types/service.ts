// Mirrors the Service Status Table exposed by
// server/app/api/system/network_services.py.

export type ServiceState = 'OK' | 'WARNING' | 'CRITICAL' | 'UNKNOWN'

export type ServiceAck = {
  comment: string
  acknowledgedBy: string
  acknowledgedAt: string
}

export type ServiceRow = {
  hostname: string
  service: string
  state: ServiceState
  stateType: string
  lastCheck: string | null
  checkLatency: number
  pluginOutput: string
  isFlapping: boolean
  inDowntime: boolean
  nagiosAck: string
  ack: ServiceAck | null
}

type ServiceAckApiRecord = {
  comment: string
  acknowledged_by: string
  acknowledged_at: string
}

type ServiceApiRecord = {
  hostname: string
  service: string
  state: string
  state_type: string
  last_check: string | null
  check_latency: number
  plugin_output: string
  is_flapping: boolean
  in_downtime: boolean
  nagios_ack: string
  ack: ServiceAckApiRecord | null
}

export function fromServiceRecord(record: ServiceApiRecord): ServiceRow {
  return {
    hostname: record.hostname,
    service: record.service,
    // ServiceStateType.value is "Ok"/"Warning"/"Critical"/"Unknown" (title
    // case), same class of casing quirk found on the host status endpoint —
    // normalize to uppercase so the frontend can treat this as a stable enum.
    state: record.state.toUpperCase() as ServiceState,
    stateType: record.state_type,
    lastCheck: record.last_check,
    checkLatency: record.check_latency,
    pluginOutput: record.plugin_output,
    isFlapping: record.is_flapping,
    inDowntime: record.in_downtime,
    nagiosAck: record.nagios_ack,
    ack: record.ack
      ? {
          comment: record.ack.comment,
          acknowledgedBy: record.ack.acknowledged_by,
          acknowledgedAt: record.ack.acknowledged_at,
        }
      : null,
  }
}

export type ServiceListResponse = {
  items: ServiceApiRecord[]
  page: number
  per_page: number
  pages: number
  total: number
  has_next: boolean
  has_prev: boolean
}
