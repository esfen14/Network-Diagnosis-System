import { useEffect, useState } from 'react'
import { AlertTriangle, Loader2, Plus, X } from 'lucide-react'

import { SettingsCard } from './SettingsCard'
import { SettingsActions } from './SettingsActions'
import { errorMessage } from '../../lib/api'
import { getPluginSettings, saveSnmpSettings } from '../../lib/pluginSettingsApi'
import type { SnmpOid, SnmpSettingsSection } from '../../types/pluginSettings'

// Same rules as server/app/network_discovery/plugin_settings.py.
const METRIC_PATTERN = /^[a-z0-9][a-z0-9_]{0,31}$/
const OID_PATTERN = /^\.?[0-9]+(\.[0-9]+)+$/
const MAX_OIDS = 50

// Plugin Manager states in which the plugin's services are generated.
const RUNNING_STATUSES = ['Enabled', 'Active']

const inputClass =
  'w-full rounded-xl border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--text)] outline-none focus:border-[#ffb100]'

// The first problem with the table, or null when it can be saved.
function tableError(oids: SnmpOid[]): string | null {
  if (oids.length === 0) return 'Add at least one OID. To stop SNMP checks, disable check_snmp in Plugin Manager.'
  if (oids.length > MAX_OIDS) return `At most ${MAX_OIDS} OIDs are allowed.`
  const metrics = new Set<string>()
  const seen = new Set<string>()
  for (const { metric, oid } of oids) {
    if (!METRIC_PATTERN.test(metric)) {
      return `Description "${metric}" must use only lowercase letters, digits and '_' (32 characters at most).`
    }
    if (!OID_PATTERN.test(oid)) return `OID for "${metric}" must be numeric and dotted, e.g. 1.3.6.1.2.1.1.3.0.`
    if (metrics.has(metric)) return `Description "${metric}" is used more than once.`
    if (seen.has(oid.replace(/^\./, ''))) return `OID ${oid} is listed more than once.`
    metrics.add(metric)
    seen.add(oid.replace(/^\./, ''))
  }
  return null
}

interface SnmpOidTableProps {
  oids: SnmpOid[]
  savedMetrics: Set<string>
  onChange: (oids: SnmpOid[]) => void
}

// The OID table: each row's description and OID edit in place; an add row below.
function SnmpOidTable({ oids, savedMetrics, onChange }: SnmpOidTableProps) {
  const [metric, setMetric] = useState('')
  const [oid, setOid] = useState('')
  const [error, setError] = useState<string | null>(null)

  const update = (index: number, changes: Partial<SnmpOid>) => {
    onChange(oids.map((entry, i) => (i === index ? { ...entry, ...changes } : entry)))
  }

  const add = () => {
    const entry = { metric: metric.trim().toLowerCase(), oid: oid.trim() }
    const problem = tableError([...oids, entry])
    if (problem) {
      setError(problem)
      return
    }
    onChange([...oids, entry])
    setMetric('')
    setOid('')
    setError(null)
  }

  const renamed = oids.some((entry) => !savedMetrics.has(entry.metric))

  return (
    <div>
      <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--text-muted)]">
              <th className="px-3 py-2 font-medium">Description</th>
              <th className="px-3 py-2 font-medium">OID</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {oids.length === 0 && (
              <tr>
                <td colSpan={3} className="px-3 py-3 text-xs text-[var(--text-muted)]">No OIDs. Add at least one.</td>
              </tr>
            )}
            {oids.map((entry, index) => (
              <tr key={index} className="border-b border-[var(--border)] last:border-0">
                <td className="px-2 py-1.5">
                  <input
                    aria-label={`Description ${index + 1}`}
                    value={entry.metric}
                    onChange={(e) => update(index, { metric: e.target.value.toLowerCase() })}
                    className={`${inputClass} font-mono text-xs`}
                  />
                </td>
                <td className="px-2 py-1.5">
                  <input
                    aria-label={`OID ${index + 1}`}
                    value={entry.oid}
                    onChange={(e) => update(index, { oid: e.target.value.trim() })}
                    className={`${inputClass} font-mono text-xs`}
                  />
                </td>
                <td className="px-2 py-1.5 text-right">
                  <button
                    type="button"
                    aria-label={`Remove ${entry.metric || `OID ${index + 1}`}`}
                    onClick={() => onChange(oids.filter((_, i) => i !== index))}
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

      <div className="mt-3 flex flex-wrap gap-2 sm:flex-nowrap">
        <input
          aria-label="New OID description"
          value={metric}
          placeholder="Description, e.g. uptime"
          onChange={(e) => { setMetric(e.target.value); setError(null) }}
          className={inputClass}
        />
        <input
          aria-label="New OID"
          value={oid}
          placeholder="OID, e.g. 1.3.6.1.2.1.1.3.0"
          onChange={(e) => { setOid(e.target.value); setError(null) }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          className={inputClass}
        />
        <button
          type="button"
          aria-label="Add OID"
          onClick={add}
          className="flex items-center rounded-xl border border-[var(--border)] px-3 text-[var(--text-muted)] transition hover:bg-[var(--hover)]"
        >
          <Plus size={15} />
        </button>
      </div>
      {error && <p className="mt-1.5 text-xs text-red-500">{error}</p>}
      {renamed && (
        <p className="mt-3 text-xs text-amber-600 dark:text-amber-300">
          A new or renamed description creates a new Nagios service on every SNMP device; a removed or
          renamed one stops its service, and that service&apos;s history is not carried over.
        </p>
      )}
    </div>
  )
}

function SnmpSettings({ section, onSaved }: { section: SnmpSettingsSection; onSaved: (section: SnmpSettingsSection) => void }) {
  const saved = section.settings.oids
  const [draft, setDraft] = useState<SnmpOid[]>(saved)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const hasChanges = JSON.stringify(draft) !== JSON.stringify(saved)
  const running = section.status !== null && RUNNING_STATUSES.includes(section.status)

  const handleSave = async () => {
    const problem = tableError(draft)
    if (problem) {
      setSaveError(problem)
      return
    }
    setIsSaving(true)
    setSaveError(null)
    setNotice(null)
    try {
      const result = await saveSnmpSettings(draft, section.version)
      if (result.config_ok === false) {
        setNotice(`The OIDs were saved but Nagios was not updated: ${result.config_message}`)
      }
      setDraft(result.settings.oids)
      onSaved(result)
    } catch (err) {
      setSaveError(errorMessage(err, 'Unable to save the SNMP OIDs.'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <SettingsCard
      title="SNMP OIDs"
      description="The OIDs check_snmp reads from every SNMP device. Each row becomes one Nagios service on each device, named after its description (snmp-<description>-161-udp). Saving updates Nagios straight away."
    >
      {!running && (
        <div className="mb-5 flex items-center gap-2 rounded-xl border border-amber-300/50 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
          <AlertTriangle size={16} />
          check_snmp is {section.status ?? 'not enabled'}. The OIDs are used once it is enabled in Plugin Manager.
        </div>
      )}

      <SnmpOidTable
        oids={draft}
        savedMetrics={new Set(saved.map((entry) => entry.metric))}
        onChange={(oids) => { setDraft(oids); setSaveError(null) }}
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
        onReset={() => { setDraft(section.defaults.oids); setSaveError(null) }}
        isSaving={isSaving}
        saveError={saveError}
      />
    </SettingsCard>
  )
}

export function PluginSettings() {
  const [snmp, setSnmp] = useState<SnmpSettingsSection | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    getPluginSettings()
      .then((data) => { setSnmp(data.snmp); setLoadError(null) })
      .catch((err) => setLoadError(errorMessage(err, 'Unable to load plugin settings.')))
  }, [])

  if (loadError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
        {loadError}
      </div>
    )
  }

  if (!snmp) {
    return (
      <div className="flex items-center text-sm text-[var(--text-muted)]">
        <Loader2 size={16} className="mr-2 animate-spin" /> Loading plugin settings…
      </div>
    )
  }

  if (!snmp.installed) {
    return (
      <SettingsCard title="Plugins" description="Network-wide settings for the plugins Network Discovery configures.">
        <p className="text-sm text-[var(--text-muted)]">
          No plugin with settings is installed. The SNMP OID table appears here once check_snmp is installed in
          Plugin Manager.
        </p>
      </SettingsCard>
    )
  }

  return (
    <div className="space-y-6">
      <SnmpSettings section={snmp} onSaved={setSnmp} />
    </div>
  )
}
