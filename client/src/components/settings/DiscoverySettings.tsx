import { useEffect, useState } from 'react'
import { AlertTriangle, Loader2, Plus, X } from 'lucide-react'

import { SettingsCard } from './SettingsCard'
import { SettingsActions } from './SettingsActions'
import { errorMessage } from '../../lib/api'
import { getDiscoverySettings, saveDiscoverySettings } from '../../lib/discoverySettingsApi'
import type { DiscoveryPort, DiscoverySettingsValues, PortResolution } from '../../types/discoverySettings'

const NETWORK_PATTERN = /^\d{1,3}(\.\d{1,3}){3}(\/\d{1,2})?$/
const PORT_PATTERN = /^\d{1,5}(-\d{1,5})?$/
const SERVICE_NAME_PATTERN = /^[a-z0-9][a-z0-9_-]{0,31}$/

function toValues(data: DiscoverySettingsValues): DiscoverySettingsValues {
  return {
    networks: data.networks,
    tcpPorts: data.tcpPorts,
    udpPorts: data.udpPorts,
    tcpPortServices: data.tcpPortServices,
    udpPortServices: data.udpPortServices,
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

interface PortServicesEditorProps {
  label: string
  description: string
  services: Record<string, string>
  // The table as last saved and which check each saved entry leads to.
  savedServices: Record<string, string>
  resolution: Record<string, PortResolution>
  // A port whose entry is fixed (NCPA's on TCP): shown, never edited.
  lockedPort?: number
  onChange: (services: Record<string, string>) => void
}

function describeResolution(resolution: PortResolution | undefined) {
  if (!resolution) return { text: 'Known after saving', tone: 'text-[var(--text-muted)]' }
  if (resolution.kind === 'plugin') return { text: resolution.plugin ?? '', tone: 'text-[var(--text)]' }
  if (resolution.kind === 'generic') {
    return { text: `${resolution.plugin} (generic TCP check)`, tone: 'text-amber-600 dark:text-amber-300' }
  }
  return { text: 'Skipped (no UDP check for this service)', tone: 'text-amber-600 dark:text-amber-300' }
}

// Port -> expected service table with the check each entry leads to and an add row.
function PortServicesEditor({ label, description, services, savedServices, resolution, lockedPort, onChange }: PortServicesEditorProps) {
  const [port, setPort] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const entries = Object.entries(services).sort(([a], [b]) => Number(a) - Number(b))

  const add = () => {
    const portValue = port.trim()
    const nameValue = name.trim().toLowerCase()
    const portNumber = Number(portValue)
    if (!/^\d+$/.test(portValue) || portNumber < 1 || portNumber > 65535) {
      setError('Port must be a number from 1 to 65535.')
      return
    }
    if (portNumber === lockedPort) {
      setError(`Port ${portNumber} is NCPA's port and always maps to ncpa.`)
      return
    }
    if (!SERVICE_NAME_PATTERN.test(nameValue)) {
      setError("Service name must be letters, digits, '-' or '_'.")
      return
    }
    onChange({ ...services, [String(portNumber)]: nameValue })
    setPort('')
    setName('')
    setError(null)
  }

  const remove = (key: string) => {
    const next = { ...services }
    delete next[key]
    onChange(next)
  }

  return (
    <div>
      <p className="text-sm font-medium text-[var(--text)]">{label}</p>
      <p className="mt-0.5 text-xs text-[var(--text-muted)]">{description}</p>

      <div className="mt-3 overflow-hidden rounded-xl border border-[var(--border)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-left text-xs text-[var(--text-muted)]">
              <th className="px-3 py-2 font-medium">Port</th>
              <th className="px-3 py-2 font-medium">Expected service</th>
              <th className="px-3 py-2 font-medium">Checked by</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-3 text-xs text-[var(--text-muted)]">No entries.</td>
              </tr>
            )}
            {entries.map(([key, value]) => {
              const locked = Number(key) === lockedPort
              const unchanged = savedServices[key] === value
              const check = describeResolution(unchanged ? resolution[key] : undefined)
              return (
                <tr key={key} className="border-b border-[var(--border)] last:border-0">
                  <td className="px-3 py-2 text-[var(--text)]">{key}</td>
                  <td className="px-3 py-2 font-mono text-xs text-[var(--text)]">{value}</td>
                  <td className={`px-3 py-2 text-xs ${check.tone}`}>{check.text}</td>
                  <td className="px-2 py-2 text-right">
                    {locked ? (
                      <span className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">Fixed</span>
                    ) : (
                      <button
                        type="button"
                        aria-label={`Remove ${label} service for port ${key}`}
                        onClick={() => remove(key)}
                        className="text-[var(--text-muted)] hover:text-red-500"
                      >
                        <X size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
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
          aria-label={`Add ${label} service`}
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
  const [ncpaPort, setNcpaPort] = useState<number | undefined>(undefined)
  const [resolution, setResolution] = useState<{ tcp: Record<string, PortResolution>; udp: Record<string, PortResolution> }>({ tcp: {}, udp: {} })
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
        setNcpaPort(data.settings.ncpaPort)
        setResolution(data.settings.resolution)
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
      setNcpaPort(result.ncpaPort)
      setResolution(result.resolution)
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
        title="Port → Service"
        description="The service you expect on each port. A port nmap cannot identify is treated as this service. If nmap identifies a different service there, it is not relabelled: the port is flagged as not used as intended and is not monitored until you acknowledge it. Monitoring starts only when the plugin that checks the service is enabled in Plugin Manager. To fix one device's port, pin it on that device instead."
      >
        <div className="grid gap-8 lg:grid-cols-2">
          <PortServicesEditor
            label="TCP"
            description="Expected service for this TCP port on every device. NCPA's port is fixed."
            services={draft.tcpPortServices}
            savedServices={saved.tcpPortServices}
            resolution={resolution.tcp}
            lockedPort={ncpaPort}
            onChange={(services) => update({ tcpPortServices: services })}
          />
          <PortServicesEditor
            label="UDP"
            description="Expected service for this UDP port on every device."
            services={draft.udpPortServices}
            savedServices={saved.udpPortServices}
            resolution={resolution.udp}
            onChange={(services) => update({ udpPortServices: services })}
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
