export type DiscoveryPort = number | string

// Which check a Port -> Service entry leads to: a plugin of its own, the
// generic TCP check, or nothing (a UDP service without a check is skipped).
export type PortResolution = {
  plugin: string | null
  kind: 'plugin' | 'generic' | 'skipped'
}

export type DiscoverySettingsValues = {
  networks: string[]
  tcpPorts: DiscoveryPort[]
  udpPorts: DiscoveryPort[]
  // The service expected on each port. The TCP table always holds NCPA's port.
  tcpPortServices: Record<string, string>
  udpPortServices: Record<string, string>
}

type DiscoveryDerived = {
  ncpaPort: number
  resolution: { tcp: Record<string, PortResolution>; udp: Record<string, PortResolution> }
}

export type DiscoverySettings = DiscoverySettingsValues & DiscoveryDerived & {
  version: number
  updatedAt: string | null
}

export type DiscoverySettingsResponse = {
  settings: DiscoverySettings
  defaults: DiscoverySettingsValues & DiscoveryDerived
  scanRunning: boolean
}
