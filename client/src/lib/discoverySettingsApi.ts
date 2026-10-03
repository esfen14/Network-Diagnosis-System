// Wrappers around server/app/api/system/discovery_settings.py.
import { apiGet, apiPut } from './api'
import type { DiscoverySettings, DiscoverySettingsResponse, DiscoverySettingsValues } from '../types/discoverySettings'

export function getDiscoverySettings() {
  return apiGet<DiscoverySettingsResponse>('/api/system/discovery-settings')
}

export function saveDiscoverySettings(values: DiscoverySettingsValues, version: number) {
  return apiPut<DiscoverySettings>('/api/system/discovery-settings', { ...values, version })
}
