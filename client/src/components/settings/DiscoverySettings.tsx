import { useEffect, useState } from 'react'
import { AlertTriangle, Loader2, Plus, X } from 'lucide-react'

import { SettingsCard } from './SettingsCard'
import { SettingsActions } from './SettingsActions'
import { errorMessage } from '../../lib/api'
import { getDiscoverySettings, saveDiscoverySettings } from '../../lib/discoverySettingsApi'
import type { DiscoveryPort, DiscoverySettingsValues } from '../../types/discoverySettings'

const NETWORK_PATTERN = /^\d{1,3}(\.\d{1,3}){3}(\/\d{1,2})?$/
const PORT_PATTERN = /^\d{1,5}(-\d{1,5})?$/
const SERVICE_NAME_PATTERN = /^[a-z0-9][a-z0-9_-]{0,31}$/

function toValues(data: DiscoverySettingsValues): DiscoverySettingsValues {
  return {
    networks: data.networks,
    tcpPorts: data.tcpPorts,
    udpPorts: data.udpPorts,
    tcpServiceOverrides: data.tcpServiceOverrides,
    udpServiceOverrides: data.udpServiceOverrides,
  }
}

function parsePort(value: string): DiscoveryPort {
  return /^\d+$/.test(value) ? Number(value) : value
}

const inputClass =
  'w-full rounded-xl border border-[var(--border)] bg-transparent px-3 py-2 text-sm text-[var(--text)] outline-none focus:border-[#ffb100]'

interface ListEditorProps {
  label: string
  description: string
  placeholder: string
  items: DiscoveryPort[]
  isValid: (value: string) => boolean
  invalidMessage: string
  emptyMessage: string
  onChange: (items: DiscoveryPort[]) => void
}

function ListEditor({ label, description, placeholder, items, isValid, invalidMessage, emptyMessage, onChange }: ListEditorProps) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)

  const add = () => {
    const value = draft.trim()
    if (!value) return
    if (!isValid(value)) {
      setError(invalidMessage)
      return
    }
    if (items.some((item) => String(item) === value)) {
      setError(`${value} is already in the list.`)
      return
    }
    onChange([...items, parsePort(value)])
    setDraft('')
    setError(null)
  }

  return (
    <div>
      <p className="text-sm font-medium text-[var(--text)]">{label}</p>
      <p className="mt-0.5 text-xs text-[var(--text-muted)]">{description}</p>

      <div className="mt-3 flex flex-wrap gap-2">
        {items.length === 0 && <span className="text-xs text-[var(--text-muted)]">{emptyMessage}</span>}
        {items.map((item) => (
          <span key={String(item)} className="flex items-center gap-1 rounded-full bg-[var(--hover)] px-3 py-1 text-xs text-[var(--text)]">
            {item}
            <button
              type="button"
              aria-label={`Remove ${item}`}
              onClick={() => onChange(items.filter((other) => other !== item))}
              className="text-[var(--text-muted)] hover:text-red-500"
            >
              <X size={12} />
            </button>
          </span>
        ))}
      </div>

      <div className="mt-3 flex gap-2">
        <input
          aria-label={`Add ${label}`}
          value={draft}
          placeholder={placeholder}
          onChange={(e) => { setDraft(e.target.value); setError(null) }}
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
          aria-label={`Add to ${label}`}
          onClick={add}
          className="flex items-center rounded-xl border border-[var(--border)] px-3 text-[var(--text-muted)] transition hover:bg-[var(--hover)]"
        >
          <Plus size={15} />
        </button>
      </div>
      {error && <p className="mt-1.5 text-xs text-red-500">{error}</p>}
    </div>
  )
}

interface OverridesEditorProps {
  label: string
  overrides: Record<string, string>
  onChange: (overrides: Record<string, string>) => void
}

// Port -> service name table with an add row.
function OverridesEditor({ label, overrides, onChange }: OverridesEditorProps) {
  const [port, setPort] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const entries = Object.entries(overrides).sort(([a], [b]) => Number(a) - Number(b))

  const add = () => {
    const portValue = port.trim()
    const nameValue = name.trim()
    const portNumber = Number(portValue)
    if (!/^\d+$/.test(portValue) || portNumber < 1 || portNumber > 65535) {
      setError('Port must be a number from 1 to 65535.')
      return
    }
    if (!SERVICE_NAME_PATTERN.test(nameValue)) {
      setError("Service name must be lowercase letters, digits, '-' or '_'.")
      return
    }
    onChange({ ...overrides, [String(portNumber)]: nameValue })
    setPort('')
    setName('')
    setError(null)
  }

  const remove = (key: string) => {
    const next = { ...overrides }
    delete next[key]
    onChange(next)
  }

  return (
    <div>
      <p className="text-sm font-medium text-[var(--text)]">{label}</p>
      <p className="mt-0.5 text-xs text-[var(--text-muted)]">
        Name given to a service found on this port, replacing what nmap reports.
      </p>

      <div className="mt-3 overflow-hidden rounded-xl border border-[var(--border)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--text-muted)]">
              <th className="px-3 py-2 font-medium">Port</th>
              <th className="px-3 py-2 font-medium">Service name</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td colSpan={3} className="px-3 py-3 text-xs text-[var(--text-muted)]">No overrides.</td>
              </tr>
            )}
            {entries.map(([key, value]) => (
              <tr key={key} className="border-b border-[var(--border)] last:border-0">
                <td className="px-3 py-2 text-[var(--text)]">{key}</td>
                <td className="px-3 py-2 font-mono text-xs text-[var(--text)]">{value}</td>
                <td className="px-2 py-2 text-right">
                  <button
                    type="button"
                    aria-label={`Remove ${label} override for port ${key}`}
                    onClick={() => remove(key)}
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

      <div className="mt-3 flex gap-2">
        <input
          aria-label={`${label} port`}
          value={port}
          placeholder="Port"
          inputMode="numeric"
          onChange={(e) => { setPort(e.target.value); setError(null) }}
          className={`${inputClass} max-w-[110px]`}
        />
        <input
          aria-label={`${label} service name`}
          value={name}
          placeholder="Service name, e.g. ssh"
          onChange={(e) => { setName(e.target.value); setError(null) }}
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
          aria-label={`Add ${label} override`}
          onClick={add}
          className="flex items-center rounded-xl border border-[var(--border)] px-3 text-[var(--text-muted)] transition hover:bg-[var(--hover)]"
        >
          <Plus size={15} />
        </button>
      </div>
      {error && <p className="mt-1.5 text-xs text-red-500">{error}</p>}
    </div>
  )
}

export function DiscoverySettings() {
  const [saved, setSaved] = useState<DiscoverySettingsValues | null>(null)
  const [draft, setDraft] = useState<DiscoverySettingsValues | null>(null)
  const [defaults, setDefaults] = useState<DiscoverySettingsValues | null>(null)
  const [version, setVersion] = useState(0)
  const [scanRunning, setScanRunning] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    getDiscoverySettings()
      .then((data) => {
        const values = toValues(data.settings)
        setSaved(values)
        setDraft(values)
        setDefaults(data.defaults)
        setVersion(data.settings.version)
        setScanRunning(data.scanRunning)
        setLoadError(null)
      })
      .catch((err) => setLoadError(errorMessage(err, 'Unable to load discovery settings.')))
  }, [])

  if (loadError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
        {loadError}
      </div>
    )
  }

  if (!draft || !saved) {
    return (
      <div className="flex items-center text-sm text-[var(--text-muted)]">
        <Loader2 size={16} className="mr-2 animate-spin" /> Loading discovery settings…
      </div>
    )
  }

  const update = (changes: Partial<DiscoverySettingsValues>) => {
    setDraft({ ...draft, ...changes })
    setSaveError(null)
  }

  const hasChanges = JSON.stringify(draft) !== JSON.stringify(saved)

  const handleSave = async () => {
    if (draft.networks.length === 0) {
      setSaveError('Add at least one network to scan.')
      return
    }
    setIsSaving(true)
    setSaveError(null)
    try {
      const result = await saveDiscoverySettings(draft, version)
      const values = toValues(result)
      setSaved(values)
      setDraft(values)
      setVersion(result.version)
    } catch (err) {
      setSaveError(errorMessage(err, 'Unable to save discovery settings.'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      {scanRunning && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-300/50 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
          <AlertTriangle size={16} />
          A network discovery scan is running. Changes can be saved once it finishes.
        </div>
      )}

      <SettingsCard
        title="Networks & Ports"
        description="What Network Discovery scans. Changes apply from the next scan."
      >
        <div className="grid gap-x-8 gap-y-8 lg:grid-cols-3">
          <ListEditor
            label="Networks"
            description="IPv4 ranges in CIDR form, /16 or smaller. Localhost is never scanned."
            placeholder="192.168.1.0/24"
            items={draft.networks}
            isValid={(value) => NETWORK_PATTERN.test(value)}
            invalidMessage="Enter an IPv4 address or range, e.g. 192.168.1.0/24."
            emptyMessage="No networks. Add at least one."
            onChange={(items) => update({ networks: items.map(String) })}
          />
          <ListEditor
            label="TCP Ports"
            description="Single ports or ranges. Leave empty to use nmap's default ports."
            placeholder="22 or 1-1024"
            items={draft.tcpPorts}
            isValid={(value) => PORT_PATTERN.test(value)}
            invalidMessage="Enter a port (1-65535) or a range like 1-1024."
            emptyMessage="nmap default ports"
            onChange={(items) => update({ tcpPorts: items })}
          />
          <ListEditor
            label="UDP Ports"
            description="Single ports or ranges. UDP scans are slow, so keep this list short."
            placeholder="161"
            items={draft.udpPorts}
            isValid={(value) => PORT_PATTERN.test(value)}
            invalidMessage="Enter a port (1-65535) or a range like 1-1024."
            emptyMessage="nmap default ports"
            onChange={(items) => update({ udpPorts: items })}
          />
        </div>
      </SettingsCard>

      <SettingsCard
        title="Service Name Overrides"
        description="Well-known ports whose detected service should be renamed before Nagios checks are generated."
      >
        <div className="grid gap-8 lg:grid-cols-2">
          <OverridesEditor
            label="TCP"
            overrides={draft.tcpServiceOverrides}
            onChange={(overrides) => update({ tcpServiceOverrides: overrides })}
          />
          <OverridesEditor
            label="UDP"
            overrides={draft.udpServiceOverrides}
            onChange={(overrides) => update({ udpServiceOverrides: overrides })}
          />
        </div>

        <SettingsActions
          hasChanges={hasChanges && !scanRunning}
          onSave={handleSave}
          onDiscard={() => { setDraft(saved); setSaveError(null) }}
          onReset={defaults ? () => update(toValues(defaults)) : undefined}
          isSaving={isSaving}
          saveError={saveError}
        />
      </SettingsCard>
    </div>
  )
}
