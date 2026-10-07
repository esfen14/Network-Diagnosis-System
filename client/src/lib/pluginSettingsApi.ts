// Wrappers around server/app/api/system/plugin_settings.py.
import { apiGet, apiPut } from './api'
import type { PluginSettingsResponse, SnmpOid, SnmpSaveResponse } from '../types/pluginSettings'

export function getPluginSettings() {
  return apiGet<PluginSettingsResponse>('/api/system/plugin-settings')
}

export function saveSnmpSettings(oids: SnmpOid[], version: number) {
  return apiPut<SnmpSaveResponse>('/api/system/plugin-settings/snmp', { oids, version })
}
