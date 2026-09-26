// Types mirror server/app/plugin_models.py enums and the JSON shapes
// documented in the Plugin Manager route reference (server/app/api/plugin/manager.py).

export type PluginType = 'Nagios' | 'Custom'

export type PluginSource = 'Baseline (ISO)' | 'Administrator Added'

export type PluginStatus =
  | 'Available'
  | 'Ready'
  | 'Installed'
  | 'Enabled'
  | 'Active'
  | 'Disabled'
  | 'Update Available'
  | 'Validation Failed'
  | 'Dependency Failed'
  | 'Installation Failed'
  | 'Configuration Failed'
  | 'Rollback'

export const FAILED_STATUSES: PluginStatus[] = [
  'Validation Failed',
  'Dependency Failed',
  'Installation Failed',
  'Configuration Failed',
]

export type PluginListItem = {
  id: number
  name: string
  display_name: string | null
  category: string | null
  type: PluginType
  source: PluginSource
  status: PluginStatus
  current_version: string | null
  updated_at: string
}

export type PluginListResponse = {
  items: PluginListItem[]
  page: number
  per_page: number
  pages: number
  total: number
  has_next: boolean
  has_prev: boolean
}

// One monitoring check live in Nagios: a plugin applied to a target device
// (GET /api/plugin/running).
export type RunningCheck = {
  id: number
  plugin: {
    id: number
    name: string
    display_name: string | null
    status: PluginStatus
  }
  target: {
    id: number
    hostname: string | null
    ip_address: string
  } | null
  service_description: string | null
  applied_at: string
}

export type RunningChecksResponse = {
  items: RunningCheck[]
  page: number
  per_page: number
  pages: number
  total: number
  has_next: boolean
  has_prev: boolean
}

export type PluginSummary = {
  installed_plugins: number
  active_capabilities: number
  custom_plugins: number
  updates_available: number
  validation_issues: number
}

export type PluginMonitoringUsage = {
  services: number
  devices: number
  placeholder: boolean
  note: string
}

export type PluginDetails = {
  id: number
  name: string
  display_name: string | null
  description: string | null
  author: string | null
  category: string | null
  type: PluginType
  source: PluginSource
  status: PluginStatus
  current_version: string | null
  executable_path: string
  created_at: string
  updated_at: string
  commands_count: number
  dependencies_count: number
  rollback_available: boolean
  monitoring_usage: PluginMonitoringUsage
}

export type PluginCommand = {
  id: number
  command_name: string
  default_command: string
  active_command: string
  is_overridden: boolean
  is_default: boolean
}

export type DependencyStatus = 'Ok' | 'Missing' | 'Incompatible'

export type PluginDependency = {
  id: number
  name: string
  type: 'Binary' | 'Library' | 'Package' | 'Runtime' | 'Capability'
  required_version: string | null
  status: DependencyStatus
}

export type ScanStatusValue = 'Running' | 'Success' | 'Failed'

export type PluginScanStatus = {
  id: number
  status: ScanStatusValue
  progress: number
  message: string
  start_at: string
  completed_at: string | null
  error: string | null
}

export type PluginHistoryEntry = {
  id: number
  plugin_id: number
  plugin_name: string
  action: string
  administrator: string
  result: 'Success' | 'Failed'
  performed_at: string
  message: string
}

export type PluginHistoryResponse = {
  items: PluginHistoryEntry[]
  page: number
  per_page: number
  pages: number
  total: number
  has_next: boolean
  has_prev: boolean
}

export type PluginTransitionResult = {
  id: number
  status: PluginStatus
  changed: boolean
}

export type CustomPluginCheckResult = {
  name: string
  passed: boolean
  message: string
}

export type CustomPluginUploadResult = {
  success: boolean
  plugin: PluginListItem | null
  checks: CustomPluginCheckResult[]
  message: string
}

// POST /<id>/validate — distinct shape from PluginDetails; checks is a dict
// keyed by check name, not a list (see server/app/api/plugin/manager.py).
export type PluginValidationCheck = {
  passed: boolean
  message: string
  [extra: string]: unknown
}

export type PluginValidationResult = {
  plugin_id: number
  is_valid: boolean
  status: PluginStatus
  checks: {
    executable: PluginValidationCheck
    permissions: PluginValidationCheck
    execution: PluginValidationCheck
  }
}

// POST /<id>/update — HTTP 200 either way; data.success says whether the
// update itself worked. A failed update leaves the plugin in 'Rollback'.
export type PluginUpdateResult = {
  success: boolean
  plugin_id: number
  status: PluginStatus
  rollback_available: boolean
  previous_version?: string | null
  current_version?: string | null
  failed_step?: string
  validation?: PluginValidationResult | Record<string, unknown>
  nagios_check?: { passed: boolean; output: string }
}

export type PluginRollbackResult = {
  success: boolean
  plugin_id: number
  status: PluginStatus
  restored_version: string | null
}

export type PluginConfigurationStatus = 'Pending' | 'Applied' | 'Failed'

export type PluginTarget = {
  id: number
  hostname: string | null
  ip_address: string
}

export type PluginConfiguration = {
  id: number
  target: PluginTarget | null
  service_description: string
  status: PluginConfigurationStatus
  configuration_data: unknown
  updated_at: string
}

// POST /<id>/configurations — HTTP 200 either way; data.success says
// whether the configuration was applied to Nagios.
export type PluginConfigurationApplyResult = {
  success: boolean
  configuration_id: number
  status: PluginConfigurationStatus
  plugin_status?: PluginStatus
  validation_output?: string
}
