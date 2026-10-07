// Settings -> Plugins (server/app/api/system/plugin_settings.py). Each row of a plugin's table
// becomes a Nagios service on every device the plugin checks, named <plugin>-<metric>-<port>-<protocol>.

// The plugins with a section, by registry definition name.
export type SettingsPluginName = 'snmp' | 'ncpa'

// One table row. "metric" is the description (what is measured) and is part of the service name.
// SNMP rows have "oid"; NCPA rows have "path" and the optional warning, critical, units and queryargs.
export type PluginSettingsRow = Record<string, string>

export type PluginSettingsSection = {
  plugin: string
  // The plugin has a row in Plugin Manager; the section is editable only then.
  installed: boolean
  status: string | null
  settings: Record<string, PluginSettingsRow[]>
  defaults: Record<string, PluginSettingsRow[]>
  version: number
}

export type PluginSettingsResponse = Record<SettingsPluginName, PluginSettingsSection>

export type PluginSettingsSaveResponse = PluginSettingsSection & {
  config_applied: boolean
  config_ok: boolean
  config_message: string
}
