import type { DevicePort, DevicePortsResponse, PortStateName, ServiceOption } from '../types/devicePorts'

// A Monitored ssh port as GET /api/system/hosts/<id>/ports returns it; override what a test needs.
export function port(overrides: Partial<DevicePort> = {}): DevicePort {
  return {
    protocol: 'tcp',
    number: 22,
    service_name: 'ssh',
    observed_service_name: 'ssh',
    state: 'MONITORED',
    source: 'SCAN',
    identified_by: 'FINGERPRINT',
    pinned: false,
    plugin_name: 'ssh',
    check_plugin: 'check_ssh',
    plugin_enabled: true,
    expected_service_name: null,
    mismatch_acknowledged: false,
    promotion_held: false,
    managed_by_ncpa: false,
    first_seen_at: '2026-10-01T09:00:00+00:00',
    last_seen_at: '2026-10-05T09:30:00+00:00',
    missed_scans: 0,
    reason: null,
    ...overrides,
  }
}

export const OPTIONS: ServiceOption[] = [
  { name: 'http', plugin: 'check_http', protocols: ['tcp'] },
  { name: 'ssh', plugin: 'check_ssh', protocols: ['tcp'] },
  { name: 'snmp', plugin: 'check_snmp', protocols: ['udp'] },
]

const STATES: PortStateName[] = ['MONITORED', 'MISSING', 'SUGGESTED', 'IGNORED', 'ARCHIVED']

export function ports(list: DevicePort[], overrides: Partial<DevicePortsResponse['device']> = {}): DevicePortsResponse {
  const counts = Object.fromEntries(STATES.map((state) => [state, list.filter((p) => p.state === state).length]))
  return {
    device: { id: 4, nagios_host_name: 'web-01', ip_address: '192.168.130.20', state: 'ACTIVE', scanned: true, ...overrides },
    ports: list,
    counts: counts as DevicePortsResponse['counts'],
    service_options: OPTIONS,
  }
}
