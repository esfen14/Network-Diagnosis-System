export type DiscoveryPort = number | string

export type DiscoverySettingsValues = {
  networks: string[]
  tcpPorts: DiscoveryPort[]
  udpPorts: DiscoveryPort[]
  tcpServiceOverrides: Record<string, string>
  udpServiceOverrides: Record<string, string>
}

export type DiscoverySettings = DiscoverySettingsValues & {
  version: number
  updatedAt: string | null
}

export type DiscoverySettingsResponse = {
  settings: DiscoverySettings
  defaults: DiscoverySettingsValues
  scanRunning: boolean
}
