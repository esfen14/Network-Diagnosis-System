// Wrappers around the Plugin Manager routes documented in
// server/app/api/plugin/manager.py (see PinPoint_Plugin_Manager_UI_Architecture
// reference doc, Section 2 "Route Reference").
import { apiDelete, apiGet, apiPost, apiPut } from './api'
import type {
  CustomCheckChange,
  CustomCheckDevice,
  CustomCheckInput,
  CustomChecksResponse,
  CustomPluginUploadResult,
  EnablePreview,
  PluginCommand,
  PluginDependency,
  PluginDetails,
  PluginHistoryResponse,
  PluginListResponse,
  PluginScanStatus,
  PluginServicesResponse,
  PluginSummary,
  PluginTransitionResult,
  PluginValidationResult,
  ServiceMonitoringResult,
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

// What enabling would monitor, without changing anything.
export function getEnablePreview(id: number) {
  return apiGet<EnablePreview>(`/api/plugin/${id}/enable-preview`)
}

// What a plugin monitors, one row per Nagios service, with live status.
export function getPluginServices(id: number, query: { page?: number; per_page?: number; search?: string }) {
  const qs = buildQuery(query)
  return apiGet<PluginServicesResponse>(`/api/plugin/${id}/services?${qs}`)
}

// Custom checks: a plugin discovery cannot attach to a port, run against one device (Custom_Checks_Plan.md).
export function getCustomChecks(id: number, query: { page?: number; per_page?: number; search?: string }) {
  return apiGet<CustomChecksResponse>(`/api/plugin/${id}/custom-checks?${buildQuery(query)}`)
}

export function searchCustomCheckDevices(search: string) {
  return apiGet<CustomCheckDevice[]>(`/api/plugin/custom-check-devices?${buildQuery({ search })}`)
}

export function addCustomCheck(id: number, input: CustomCheckInput) {
  return apiPost<CustomCheckChange>(`/api/plugin/${id}/custom-checks`, input)
}

export function changeCustomCheck(id: number, checkId: number, input: CustomCheckInput) {
  return apiPut<CustomCheckChange>(`/api/plugin/${id}/custom-checks/${checkId}`, input)
}

export function pauseCustomCheck(id: number, checkId: number) {
  return apiPost<CustomCheckChange>(`/api/plugin/${id}/custom-checks/${checkId}/pause`)
}

export function resumeCustomCheck(id: number, checkId: number) {
  return apiPost<CustomCheckChange>(`/api/plugin/${id}/custom-checks/${checkId}/resume`)
}

export function removeCustomCheck(id: number, checkId: number) {
  return apiDelete<{ id: number; changed: boolean; message: string }>(`/api/plugin/${id}/custom-checks/${checkId}`)
}

export type ServicePortRef = { device_id: number; protocol: 'tcp' | 'udp'; port: number }

export function stopServiceMonitoring(id: number, ref: ServicePortRef) {
  return apiPost<ServiceMonitoringResult>(`/api/plugin/${id}/services/stop`, ref)
}

export function resumeServiceMonitoring(id: number, ref: ServicePortRef) {
  return apiPost<ServiceMonitoringResult>(`/api/plugin/${id}/services/resume`, ref)
}

// Used only by AddCustomPluginModal, which is disabled for now: the Add
// Custom Plugin button and POST /api/plugin/custom are commented out.
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
  void input
  throw new Error('Custom plugins are not available in this release.')
  /*
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
  */
}

export type PluginUpdateResult = {
  success: boolean
  plugin_id?: number
  status: string
  previous_version?: string | null
  current_version?: string | null
  rollback_available: boolean
  failed_step?: string
  nagios_check?: { passed: boolean; output: string }
}

export async function updatePlugin(
  id: number,
  source: { file: File } | { url: string }
): Promise<PluginUpdateResult> {
  const formData = new FormData()
  if ('file' in source) formData.append('file', source.file)
  else formData.append('url', source.url)

  const res = await fetch(`/api/plugin/${id}/update`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  })

  const text = await res.text()
  let body: { message?: string; data?: PluginUpdateResult } = {}
  try {
    body = text ? JSON.parse(text) : {}
  } catch {
    body = {}
  }
  if (!res.ok) {
    throw new Error(body.message ?? `Request failed (${res.status})`)
  }
  return (body.data ?? body) as PluginUpdateResult
}

export function rollbackPluginUpdate(id: number) {
  return apiPost<{ success: boolean; plugin_id: number; status: string; restored_version: string | null }>(
    `/api/plugin/${id}/update/rollback`
  )
}
