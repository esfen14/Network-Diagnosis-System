import { useEffect, useState } from 'react'
import { AlertTriangle, Loader2, Plus, X } from 'lucide-react'

import { SettingsCard } from './SettingsCard'
import { SettingsActions } from './SettingsActions'
import { errorMessage } from '../../lib/api'
import { getPluginSettings, savePluginSettings } from '../../lib/pluginSettingsApi'
import type { PluginSettingsRow, PluginSettingsSection, SettingsPluginName } from '../../types/pluginSettings'

// Same rules as server/app/network_discovery/plugin_settings.py.
const METRIC_PATTERN = /^[a-z0-9][a-z0-9_]{0,31}$/
const OID_PATTERN = /^\.?[0-9]+(\.[0-9]+)+$/
const NCPA_PATH_PATTERN = /^([A-Za-z0-9_.|-]+|\{partition\})(\/([A-Za-z0-9_.|-]+|\{partition\}))*$/
const THRESHOLD_PATTERN = /^@?(~|-?[0-9]+(\.[0-9]+)?)?(:(-?[0-9]+(\.[0-9]+)?)?)?$/
const UNITS_PATTERN = /^[A-Za-z%]{1,8}$/
const QUERYARGS_PATTERN = /^[A-Za-z0-9_]+=[A-Za-z0-9_.-]+(,[A-Za-z0-9_]+=[A-Za-z0-9_.-]+)*$/
const MAX_ROWS = 50

// Plugin Manager states in which the plugin's services are generated.
const RUNNING_STATUSES = ['Enabled', 'Active']

const inputClass =
  'w-full rounded-xl border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--text)] outline-none focus:border-[#ffb100]'

type Column = {
  key: string
  label: string
  placeholder: string
  // Optional columns may be left empty; the server drops them.
  optional?: boolean
  // Checks a non-empty value; returns the message for a bad one.
  check: (value: string, row: PluginSettingsRow) => string | null
  className?: string
}

type TableConfig = {
  plugin: SettingsPluginName
  // The body key the table is saved under.
  variable: string
  title: string
  description: string
  // "OID" / "metric": used in buttons and messages.
  noun: string
  // "SNMP device" / "NCPA host": what each row becomes a service on.
  target: string
  columns: Column[]
  note?: string
}

const descriptionColumn: Column = {
  key: 'metric',
  label: 'Description',
  placeholder: 'e.g. uptime',
  check: (value) =>
    METRIC_PATTERN.test(value)
      ? null
      : `Description "${value}" must use only lowercase letters, digits and '_' (32 characters at most).`,
  className: 'min-w-[150px]',
}

const SNMP_TABLE: TableConfig = {
  plugin: 'snmp',
  variable: 'oids',
  title: 'SNMP OIDs',
  description:
    'The OIDs check_snmp reads from every SNMP device. Each row becomes one Nagios service on each device, named after its description (snmp-<description>-161-udp). Saving updates Nagios straight away.',
  noun: 'OID',
  target: 'SNMP device',
  columns: [
    descriptionColumn,
    {
      key: 'oid',
      label: 'OID',
      placeholder: 'e.g. 1.3.6.1.2.1.1.3.0',
      check: (value, row) =>
        OID_PATTERN.test(value) ? null : `OID for "${row.metric}" must be numeric and dotted, e.g. 1.3.6.1.2.1.1.3.0.`,
      className: 'min-w-[220px]',
    },
  ],
}

const threshold = (label: string) => (value: string, row: PluginSettingsRow) =>
  THRESHOLD_PATTERN.test(value) ? null : `${label} for "${row.metric}" must be a Nagios threshold, e.g. 80 or 10:20.`

const NCPA_TABLE: TableConfig = {
  plugin: 'ncpa',
  variable: 'metrics',
  title: 'NCPA Metrics',
  description:
    'The metrics check_ncpa reads from every host with the NCPA agent. Each row becomes one Nagios service on each host, named after its description (ncpa-<description>-5693-tcp). Saving updates Nagios straight away.',
  noun: 'metric',
  target: 'NCPA host',
  note:
    'A path containing {partition} becomes one service per disk partition found when NCPA was installed (e.g. disk_root, disk_boot).',
  columns: [
    descriptionColumn,
    {
      key: 'path',
      label: 'Metric path',
      placeholder: 'e.g. cpu/percent',
      check: (value, row) =>
        NCPA_PATH_PATTERN.test(value.replace(/^\/+|\/+$/g, ''))
          ? null
          : `Path for "${row.metric}" must be an NCPA path such as cpu/percent or disk/logical/{partition}/used_percent.`,
      className: 'min-w-[240px]',
    },
    { key: 'warning', label: 'Warning', placeholder: 'e.g. 70', optional: true, check: threshold('Warning'), className: 'min-w-[80px]' },
    { key: 'critical', label: 'Critical', placeholder: 'e.g. 90', optional: true, check: threshold('Critical'), className: 'min-w-[80px]' },
    {
      key: 'units',
      label: 'Units',
      placeholder: 'e.g. Gi',
      optional: true,
      check: (value, row) => (UNITS_PATTERN.test(value) ? null : `Units for "${row.metric}" must be up to 8 letters or '%'.`),
      className: 'min-w-[70px]',
    },
    {
      key: 'queryargs',
      label: 'Query args',
      placeholder: 'e.g. aggregate=avg',
      optional: true,
      check: (value, row) =>
        QUERYARGS_PATTERN.test(value)
          ? null
          : `Query args for "${row.metric}" must be name=value pairs separated by ',', e.g. aggregate=avg.`,
      className: 'min-w-[140px]',
    },
  ],
}

// Every column present on every row, so inputs are controlled and drafts compare cleanly.
function normalize(rows: PluginSettingsRow[], config: TableConfig): PluginSettingsRow[] {
  return rows.map((row) => Object.fromEntries(config.columns.map((column) => [column.key, row[column.key] ?? ''])))
}

// The first problem with the table, or null when it can be saved.
function tableError(rows: PluginSettingsRow[], config: TableConfig): string | null {
  if (rows.length === 0) {
    return `Add at least one ${config.noun}. To stop these checks, disable ${config.plugin === 'snmp' ? 'check_snmp' : 'check_ncpa'} in Plugin Manager.`
  }
  if (rows.length > MAX_ROWS) return `At most ${MAX_ROWS} ${config.noun}s are allowed.`
  const metrics = new Set<string>()
  const oids = new Set<string>()
  for (const [index, row] of rows.entries()) {
    for (const column of config.columns) {
      const value = row[column.key].trim()
      if (!value) {
        if (column.optional) continue
        return `Row ${index + 1}: ${column.label} is required.`
      }
      const problem = column.check(value, row)
      if (problem) return problem
    }
    const metric = row.metric.trim()
    if (metrics.has(metric)) return `Description "${metric}" is used more than once.`
    metrics.add(metric)
    if (config.plugin === 'snmp') {
      const oid = row.oid.trim().replace(/^\./, '')
      if (oids.has(oid)) return `OID ${row.oid.trim()} is listed more than once.`
      oids.add(oid)
    }
  }
  return null
}

interface RowTableProps {
  config: TableConfig
  rows: PluginSettingsRow[]
  savedMetrics: Set<string>
  onChange: (rows: PluginSettingsRow[]) => void
}

// The editable table: every cell edits in place; "Add" appends an empty row.
function RowTable({ config, rows, savedMetrics, onChange }: RowTableProps) {
  const update = (index: number, key: string, value: string) => {
    onChange(rows.map((row, i) => (i === index ? { ...row, [key]: key === 'metric' ? value.toLowerCase() : value } : row)))
  }

  const blank = Object.fromEntries(config.columns.map((column) => [column.key, '']))
  const renamed = rows.some((row) => row.metric && !savedMetrics.has(row.metric))

  return (
    <div>
      <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--text-muted)]">
              {config.columns.map((column) => (
                <th key={column.key} className="px-3 py-2 font-medium">
                  {column.label}
                  {column.optional && <span className="ml-1 font-normal opacity-70">(optional)</span>}
                </th>
              ))}
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={config.columns.length + 1} className="px-3 py-3 text-xs text-[var(--text-muted)]">
                  No {config.noun}s. Add at least one.
                </td>
              </tr>
            )}
            {rows.map((row, index) => (
              <tr key={index} className="border-b border-[var(--border)] last:border-0">
                {config.columns.map((column) => (
                  <td key={column.key} className={`px-2 py-1.5 ${column.className ?? ''}`}>
                    <input
                      aria-label={`${column.label} ${index + 1}`}
                      value={row[column.key]}
                      placeholder={column.placeholder}
                      onChange={(e) => update(index, column.key, e.target.value)}
                      className={`${inputClass} font-mono text-xs`}
                    />
                  </td>
                ))}
                <td className="px-2 py-1.5 text-right">
                  <button
                    type="button"
                    aria-label={`Remove ${row.metric || `${config.noun} ${index + 1}`}`}
                    onClick={() => onChange(rows.filter((_, i) => i !== index))}
                    className="text-[var(--text-muted)] hover:text-red-500"
                  >
                    <X size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button
        type="button"
        onClick={() => onChange([...rows, { ...blank }])}
        disabled={rows.length >= MAX_ROWS}
        className="mt-3 flex items-center gap-1.5 rounded-xl border border-[var(--border)] px-3 py-2 text-sm text-[var(--text-muted)] transition hover:bg-[var(--hover)] disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Plus size={15} /> Add {config.noun}
      </button>

      {config.note && <p className="mt-3 text-xs text-[var(--text-muted)]">{config.note}</p>}
      {renamed && (
        <p className="mt-3 text-xs text-amber-600 dark:text-amber-300">
          A new or renamed description creates a new Nagios service on every {config.target}; a removed or
          renamed one stops its service, and that service&apos;s history is not carried over.
        </p>
      )}
    </div>
  )
}

const BANDWIDTH_ROWS = [
  { metric: 'bandwidth_in', direction: 'bytes_recv' },
  { metric: 'bandwidth_out', direction: 'bytes_sent' },
]

// Adds the two rows that feed the Network Health bandwidth card, so nobody has to know NCPA paths.
function BandwidthHelper({ rows, onChange }: { rows: PluginSettingsRow[]; onChange: (rows: PluginSettingsRow[]) => void }) {
  const [connection, setConnection] = useState('eth0')
  const [problem, setProblem] = useState<string | null>(null)
  const added = BANDWIDTH_ROWS.every((b) => rows.some((row) => row.metric === b.metric))

  const add = () => {
    const name = connection.trim()
    if (!/^[A-Za-z0-9_.|-]+$/.test(name)) {
      setProblem('Enter the connection name using letters, numbers, dots, dashes or underscores, e.g. eth0.')
      return
    }
    setProblem(null)
    const blank = Object.fromEntries(NCPA_TABLE.columns.map((column) => [column.key, '']))
    const kept = rows.filter((row) => !BANDWIDTH_ROWS.some((b) => b.metric === row.metric))
    onChange([
      ...kept,
      ...BANDWIDTH_ROWS.map((b) => ({ ...blank, metric: b.metric, path: `interface/${name}/${b.direction}`, queryargs: 'delta=1' })),
    ])
  }

  return (
    <div className="mb-5 rounded-xl border border-[var(--border)] bg-[var(--card-alt)] p-4">
      <p className="text-sm font-medium text-[var(--text)]">Show bandwidth on Network Health</p>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        This tells the system to watch how much data goes in and out of your computers. Type the name of the network
        connection they use (on most Linux computers it is <span className="font-mono">eth0</span> or <span className="font-mono">ens18</span>),
        then press the button and Save. The Bandwidth card fills in after the next check.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          aria-label="Network connection name"
          value={connection}
          onChange={(e) => { setConnection(e.target.value); setProblem(null) }}
          placeholder="e.g. eth0"
          className={`${inputClass} max-w-[200px] font-mono text-xs`}
        />
        <button
          type="button"
          onClick={add}
          className="flex items-center gap-1.5 rounded-xl border border-[var(--border)] px-3 py-2 text-sm text-[var(--text)] transition hover:bg-[var(--hover)]"
        >
          <Plus size={15} /> {added ? 'Update bandwidth rows' : 'Add bandwidth rows'}
        </button>
      </div>
      {problem && <p className="mt-2 text-xs text-red-500">{problem}</p>}
      {added && !problem && (
        <p className="mt-2 text-xs text-[var(--text-muted)]">
          Bandwidth rows are in the table below. Press Save to start watching.
        </p>
      )}
    </div>
  )
}

interface PluginSectionProps {
  config: TableConfig
  section: PluginSettingsSection
  onSaved: (section: PluginSettingsSection) => void
}

function PluginSection({ config, section, onSaved }: PluginSectionProps) {
  const saved = normalize(section.settings[config.variable] ?? [], config)
  const [draft, setDraft] = useState<PluginSettingsRow[]>(saved)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const hasChanges = JSON.stringify(draft) !== JSON.stringify(saved)
  const running = section.status !== null && RUNNING_STATUSES.includes(section.status)

  const handleSave = async () => {
    const problem = tableError(draft, config)
    if (problem) {
      setSaveError(problem)
      return
    }
    setIsSaving(true)
    setSaveError(null)
    setNotice(null)
    try {
      const result = await savePluginSettings(config.plugin, config.variable, draft, section.version)
      if (result.config_ok === false) {
        setNotice(`The ${config.noun}s were saved but Nagios was not updated: ${result.config_message}`)
      }
      setDraft(normalize(result.settings[config.variable] ?? [], config))
      onSaved(result)
    } catch (err) {
      setSaveError(errorMessage(err, `Unable to save the ${config.noun}s.`))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <SettingsCard title={config.title} description={config.description}>
      {!running && (
        <div className="mb-5 flex items-center gap-2 rounded-xl border border-amber-300/50 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
          <AlertTriangle size={16} />
          {section.plugin} is {section.status ?? 'not enabled'}. These {config.noun}s are used once it is enabled in Plugin
          Manager.
        </div>
      )}

      {config.plugin === 'ncpa' && (
        <BandwidthHelper rows={draft} onChange={(rows) => { setDraft(rows); setSaveError(null) }} />
      )}

      <RowTable
        config={config}
        rows={draft}
        savedMetrics={new Set(saved.map((row) => row.metric))}
        onChange={(rows) => { setDraft(rows); setSaveError(null) }}
      />

      {notice && (
        <p className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
          {notice}
        </p>
      )}

      <SettingsActions
        hasChanges={hasChanges}
        onSave={handleSave}
        onDiscard={() => { setDraft(saved); setSaveError(null) }}
        onReset={() => { setDraft(normalize(section.defaults[config.variable] ?? [], config)); setSaveError(null) }}
        isSaving={isSaving}
        saveError={saveError}
      />
    </SettingsCard>
  )
}

const TABLES = [SNMP_TABLE, NCPA_TABLE]

export function PluginSettings() {
  const [sections, setSections] = useState<Partial<Record<SettingsPluginName, PluginSettingsSection>> | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    getPluginSettings()
      .then((data) => { setSections(data); setLoadError(null) })
      .catch((err) => setLoadError(errorMessage(err, 'Unable to load plugin settings.')))
  }, [])

  if (loadError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
        {loadError}
      </div>
    )
  }

  if (!sections) {
    return (
      <div className="flex items-center text-sm text-[var(--text-muted)]">
        <Loader2 size={16} className="mr-2 animate-spin" /> Loading plugin settings…
      </div>
    )
  }

  const shown = TABLES.filter((config) => sections[config.plugin]?.installed)
  const missing = TABLES.filter((config) => !sections[config.plugin]?.installed)

  return (
    <div className="space-y-6">
      {shown.map((config) => (
        <PluginSection
          key={config.plugin}
          config={config}
          section={sections[config.plugin]!}
          onSaved={(section) => setSections((current) => ({ ...current, [config.plugin]: section }))}
        />
      ))}
      {missing.length > 0 && (
        <SettingsCard title={shown.length ? 'Other plugins' : 'Plugins'} description="Network-wide settings for the plugins Network Discovery configures.">
          <p className="text-sm text-[var(--text-muted)]">
            {missing.map((config) => `The ${config.title} table appears here once ${sections[config.plugin]?.plugin ?? config.plugin} is installed in Plugin Manager.`).join(' ')}
          </p>
        </SettingsCard>
      )}
    </div>
  )
}
