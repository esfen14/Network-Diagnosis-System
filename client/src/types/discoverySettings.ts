export type DiscoveryPort = number | string

export type DiscoverySettingsValues = {
  networks: string[]
  tcpPorts: DiscoveryPort[]
  udpPorts: DiscoveryPort[]
  // Fallback names, used only when nmap could not fingerprint the service.
  tcpServiceOverrides: Record<string, string>
  udpServiceOverrides: Record<string, string>
  // "Always treat port as": applied on every device whatever nmap reports.
  tcpForcedServices: Record<string, string>
  udpForcedServices: Record<string, string>
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
