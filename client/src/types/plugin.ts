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
  description: string | null
  category: string | null
  type: PluginType
  source: PluginSource
  status: PluginStatus
  current_version: string | null
  updated_at: string
  // False for plugins that check no discovered port (check_ping, check_load, ...).
  // They cannot be enabled; services attach only to ports discovery found.
  service_driven: boolean
  // Services applied for this plugin and the devices they run on.
  monitoring_usage: { services: number; devices: number }
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

export type PluginSummary = {
  installed_plugins: number
  active_capabilities: number
  // Plugins that are Enabled or Active; zero means nothing is being monitored.
  enabled_plugins: number
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
  // Official documentation page for bundled plugins; null for custom ones.
  documentation_url?: string | null
  service_driven: boolean
  // Whether and how the plugin takes custom checks (absent in older responses).
  custom_checks?: PluginCustomSupport
  type: PluginType
  source: PluginSource
  status: PluginStatus
  current_version: string | null
  executable_path: string
  created_at: string
  updated_at: string
  commands_count: number
  dependencies_count: number
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

// What the reconciler did after an enable or disable (api/plugin/reconcile.py).
export type AttachResult = {
  success: boolean
  changed?: boolean
  applied: number
  removed: number
  promoted: number
  message: string
}

export type PluginTransitionResult = {
  id: number
  status: PluginStatus
  changed: boolean
  auto_apply?: AttachResult
}

// GET /api/plugin/<id>/enable-preview: what enabling would monitor.
export type EnablePreview = {
  id: number
  name: string
  status: PluginStatus
  service_driven: boolean
  already_enabled: boolean
  matched_services: number
  matched_devices: number
  // Identified ports of this plugin that are held back (left Suggested on purpose, or at an upgrade).
  held_ports: number
  message: string
}

export type ServiceStatusKind =
  | 'ok'
  | 'warning'
  | 'critical'
  | 'unknown'
  | 'waiting'
  | 'stale'
  | 'stopped'
  | 'paused'

export type ServiceStatus = {
  kind: ServiceStatusKind
  state: string | null
  output: string
  last_check: string | null
}

// One monitored service of a plugin (GET /api/plugin/<id>/services).
export type PluginServiceItem = {
  // Null for a stopped port, which has no applied configuration.
  id: number | null
  service: string
  device: { id: number; hostname: string; ip_address: string }
  port: number
  protocol: 'tcp' | 'udp'
  metric: string | null
  monitored: boolean
  running_since: string | null
  status: ServiceStatus
}

export type CustomCheckField = {
  name: string
  flag: string
  label: string
  required: boolean
  placeholder: string
}

// Which class the plugin is in (Custom_Checks_Plan.md section 2.4) and what a custom check of it takes.
export type PluginCustomSupport = {
  class: 'service' | 'custom' | 'server' | 'credentials' | 'host' | 'stock' | 'advanced' | 'unsupported' | 'replaced' | null
  supported: boolean
  // Where a check runs: on a chosen device, or on the Nagios server itself (no device).
  target?: 'device' | 'server' | null
  // Why the plugin takes no custom check, when it does not.
  note: string | null
  fields: CustomCheckField[]
}

// One custom check of a plugin (GET /api/plugin/<id>/custom-checks).
export type CustomCheckItem = {
  id: number
  name: string
  service: string
  // The Nagios server for a server check: id null and no IP.
  device: { id: number | null; hostname: string; ip_address: string }
  variables: Record<string, string>
  paused: boolean
  running_since: string | null
  status: ServiceStatus
}

export type CustomChecksResponse = {
  items: CustomCheckItem[]
  page: number
  per_page: number
  pages: number
  total: number
  has_next: boolean
  has_prev: boolean
}

export type CustomCheckDevice = { id: number; hostname: string; ip_address: string }

// The body of an add (device_id) or change (name and variables only).
export type CustomCheckInput = {
  device_id?: number
  name: string
  variables: Record<string, string>
}

export type CustomCheckChange = CustomCheckItem & { changed: boolean; message: string }

export type PluginServicesResponse = {
  items: PluginServiceItem[]
  page: number
  per_page: number
  pages: number
  total: number
  has_next: boolean
  has_prev: boolean
}

export type ServiceMonitoringResult = {
  changed: boolean
  monitored: boolean
  auto_apply?: AttachResult
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
