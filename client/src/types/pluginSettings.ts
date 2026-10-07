// Settings -> Plugins (server/app/api/system/plugin_settings.py). Each SNMP OID entry becomes a
// Nagios service on every SNMP device, named snmp-<metric>-<port>-udp.
export type SnmpOid = {
  // The description: what the OID measures (e.g. "uptime"). Part of the service name.
  metric: string
  oid: string
}

export type SnmpSettingsSection = {
  plugin: string
  // check_snmp has a row in Plugin Manager; the section is editable only then.
  installed: boolean
  status: string | null
  settings: { oids: SnmpOid[] }
  defaults: { oids: SnmpOid[] }
  version: number
}

export type PluginSettingsResponse = {
  snmp: SnmpSettingsSection
}

export type SnmpSaveResponse = SnmpSettingsSection & {
  config_applied: boolean
  config_ok: boolean
  config_message: string
}
