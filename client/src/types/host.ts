// Mirrors the Host Status Table exposed by server/app/api/system/network_hosts.py.
// This is a Nagios host-status snapshot, not a device/asset inventory —
// there is no device type, IP, OS version, or router grouping on the backend.

export type HostState = 'UP' | 'DOWN' | 'UNREACHABLE'

export type HostAck = {
  comment: string
  acknowledgedBy: string
  acknowledgedAt: string
}

export type Host = {
  hostname: string
  state: HostState
  stateType: string
  lastCheck: string | null
  checkLatency: number
  pluginOutput: string
  isFlapping: boolean
  inDowntime: boolean
  nagiosAck: string
  ack: HostAck | null
}

type HostAckApiRecord = {
  comment: string
  acknowledged_by: string
  acknowledged_at: string
}

type HostApiRecord = {
  hostname: string
  state: string
  state_type: string
  last_check: string | null
  check_latency: number
  plugin_output: string
  is_flapping: boolean
  in_downtime: boolean
  nagios_ack: string
  ack: HostAckApiRecord | null
}

export function fromHostRecord(record: HostApiRecord): Host {
  return {
    hostname: record.hostname,
    // HostStateType.value is actually "Up"/"Down"/"Unreachable" (title case)
    // despite the route's docstring claiming UP/DOWN/UNREACHABLE — normalize
    // so the rest of the frontend can treat state as a stable uppercase enum.
    state: record.state.toUpperCase() as HostState,
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

export type HostListResponse = {
  items: HostApiRecord[]
  page: number
  per_page: number
  pages: number
  total: number
  has_next: boolean
  has_prev: boolean
}
