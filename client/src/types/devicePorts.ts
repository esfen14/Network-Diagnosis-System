// Mirrors GET /api/system/hosts/<id>/ports and the port-edit route in
// server/app/api/system/device_identity.py. Field names are kept as the API sends them (snake_case),
// as in types/plugin.ts. The behaviour they drive is in spec files/Device_Inventory_Requirements.md.

export type PortProtocol = 'tcp' | 'udp'

export type PortStateName = 'MONITORED' | 'MISSING' | 'SUGGESTED' | 'IGNORED' | 'ARCHIVED'

export type PortIdentification = 'USER' | 'PORT_RULE' | 'FINGERPRINT' | 'PORT_HINT'

// Why a Suggested or Ignored port is not monitored; the server picks exactly one (first match wins).
export type PortReasonCode =
  | 'not_used_as_intended'
  | 'held'
  | 'guessed'
  | 'no_udp_plugin'
  | 'plugin_not_enabled'
  | 'device_excluded'
  | 'pending'
  | 'stopped'

export type PortReason = {
  code: PortReasonCode
  text: string
}

export type DevicePort = {
  protocol: PortProtocol
  number: number
  service_name: string
  observed_service_name: string | null
  state: PortStateName
  source: string
  identified_by: PortIdentification | null
  // True when an administrator fixed this port's service on this device.
  pinned: boolean
  // The plugin frozen for the service when it was monitored (a registry name such as "ssh").
  plugin_name: string | null
  // The Plugin Manager plugin that checks the service, e.g. "check_ssh"; null when none can.
  check_plugin: string | null
  plugin_enabled: boolean
  expected_service_name: string | null
  mismatch_acknowledged: boolean
  promotion_held: boolean
  // The NCPA port of a device with a deployed agent: never stopped or re-pinned from here.
  managed_by_ncpa: boolean
  first_seen_at: string | null
  last_seen_at: string | null
  missed_scans: number
  reason: PortReason | null
}

export type ServiceOption = {
  name: string
  plugin: string
  protocols: PortProtocol[]
}

export type DeviceState = 'ACTIVE' | 'MISSING' | 'ADDRESS_UNKNOWN' | 'RETIRED' | 'MERGED'

export type DevicePortsResponse = {
  device: {
    id: number
    nagios_host_name: string
    ip_address: string
    state: DeviceState
    scanned: boolean
  }
  ports: DevicePort[]
  counts: Record<PortStateName, number>
  service_options: ServiceOption[]
}

// What the port-edit route accepts; send only what the action needs.
export type PortChange = {
  state?: 'MONITORED' | 'SUGGESTED' | 'IGNORED' | 'ARCHIVED'
  service_name?: string
  acknowledge_mismatch?: boolean
  unpin?: boolean
}

// What the port-edit route returns besides the port: whether a new Nagios config went live,
// whether Nagios is up to date (false means the change is saved but not in Nagios yet), and why.
export type PortChangeResult = {
  config_applied: boolean
  config_ok: boolean
  config_message: string
  port: Pick<DevicePort, 'number' | 'service_name' | 'plugin_name' | 'identified_by' | 'pinned' | 'expected_service_name' | 'mismatch_acknowledged' | 'promotion_held'> & {
    protocol: PortProtocol
    state: PortStateName
  }
}
