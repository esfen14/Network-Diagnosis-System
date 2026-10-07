// Wrappers around server/app/api/system/plugin_settings.py.
import { apiGet, apiPut } from './api'
import type {
  PluginSettingsResponse,
  PluginSettingsRow,
  PluginSettingsSaveResponse,
  SettingsPluginName,
} from '../types/pluginSettings'

export function getPluginSettings() {
  return apiGet<PluginSettingsResponse>('/api/system/plugin-settings')
}

// variable is the body key the plugin's table is saved under ("oids" for snmp, "metrics" for ncpa).
export function savePluginSettings(plugin: SettingsPluginName, variable: string, rows: PluginSettingsRow[], version: number) {
  return apiPut<PluginSettingsSaveResponse>(`/api/system/plugin-settings/${plugin}`, { [variable]: rows, version })
}
