// Wrappers around the Plugin Manager routes documented in
// server/app/api/plugin/manager.py (see PinPoint_Plugin_Manager_UI_Architecture
// reference doc, Section 2 "Route Reference").
import { apiGet, apiPost } from './api'
import type {
  CustomPluginUploadResult,
  PluginCommand,
  PluginDependency,
  PluginDetails,
  PluginHistoryResponse,
  PluginListResponse,
  PluginScanStatus,
  PluginSummary,
  PluginTransitionResult,
  PluginValidationResult,
  RunningChecksResponse,
} from '../types/plugin'

function buildQuery(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== '' && value !== undefined) search.set(key, String(value))
  })
  return search.toString()
}

export type InventoryQuery = {
  page?: number
  per_page?: number
  sort_by?: 'name' | 'type' | 'status' | 'version' | 'updated_at'
  order?: 'asc' | 'desc'
  search?: string
  type?: string
  status?: string
}

export function getPluginSummary() {
  return apiGet<PluginSummary>('/api/plugin/summary')
}

export function getPluginInventory(query: InventoryQuery) {
  const qs = buildQuery(query)
  return apiGet<PluginListResponse>(`/api/plugin?${qs}`)
}

export function getRunningChecks(query: { page?: number; per_page?: number; search?: string }) {
  const qs = buildQuery(query)
  return apiGet<RunningChecksResponse>(`/api/plugin/running?${qs}`)
}

export function getPluginDetails(id: number) {
  return apiGet<PluginDetails>(`/api/plugin/${id}`)
}

export function getPluginCommands(id: number) {
  return apiGet<PluginCommand[]>(`/api/plugin/${id}/commands`)
}

export function getPluginDependencies(id: number) {
  return apiGet<PluginDependency[]>(`/api/plugin/${id}/dependencies`)
}

export function getPluginHistory(pluginId?: number, page = 1, perPage = 10) {
  const qs = buildQuery({ plugin_id: pluginId, page, per_page: perPage })
  return apiGet<PluginHistoryResponse>(`/api/plugin/history?${qs}`)
}

export function startPluginScan() {
  return apiPost<{ message?: string }>('/api/plugin/scan')
}

export function getPluginScanStatus() {
  return apiGet<PluginScanStatus | null>('/api/plugin/scan/status')
}

export function enablePlugin(id: number) {
  return apiPost<PluginTransitionResult>(`/api/plugin/${id}/enable`)
}

export function disablePlugin(id: number) {
  return apiPost<PluginTransitionResult>(`/api/plugin/${id}/disable`)
}

export function overrideCommand(pluginId: number, commandId: number, overrideCommandText: string) {
  return apiPost<PluginCommand>(
    `/api/plugin/${pluginId}/commands/${commandId}/override`,
    { override_command: overrideCommandText }
  )
}

export function restoreDefaultCommand(pluginId: number, commandId: number) {
  return apiPost<PluginCommand>(
    `/api/plugin/${pluginId}/commands/${commandId}/restore-default`
  )
}

export function validatePlugin(id: number) {
  return apiPost<PluginValidationResult>(`/api/plugin/${id}/validate`)
}

export type AddCustomPluginInput = {
  file: File
  name: string
  commandName: string
  commandDefinition: string
  version?: string
  description?: string
  author?: string
  pluginType?: 'Nagios' | 'Custom'
  dependencies?: { name: string; type: string; required_version?: string }[]
}

export async function addCustomPlugin(input: AddCustomPluginInput): Promise<CustomPluginUploadResult> {
  const formData = new FormData()
  formData.append('file', input.file)
  formData.append('name', input.name)
  formData.append('command_name', input.commandName)
  formData.append('command_definition', input.commandDefinition)
  if (input.version) formData.append('version', input.version)
  if (input.description) formData.append('description', input.description)
  if (input.author) formData.append('author', input.author)
  if (input.pluginType) formData.append('plugin_type', input.pluginType)
  if (input.dependencies?.length) formData.append('dependencies', JSON.stringify(input.dependencies))

  const res = await fetch('/api/plugin/custom', {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })

  const text = await res.text()
  const body = text ? JSON.parse(text) : {}
  if (!res.ok) {
    throw new Error(body?.message ?? `Request failed (${res.status})`)
  }
  return (body.data ?? body) as CustomPluginUploadResult
}
