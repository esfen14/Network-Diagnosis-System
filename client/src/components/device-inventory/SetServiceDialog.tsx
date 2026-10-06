import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { DevicePort, ServiceOption } from '../../types/devicePorts'
import { SERVICE_NAME_HELP, SERVICE_NAME_RULE, checkedBy, portLabel } from './devicePortsLogic'

type Props = {
  port: DevicePort
  host: string
  options: ServiceOption[]
  // True while the request is running; the error is the server's message when it was refused.
  isSaving: boolean
  error: string | null
  onCancel: () => void
  onSave: (serviceName: string) => void
}

// "Set service…": fix what this port is on this device (requirement §6). The name is checked as the
// server checks it, the line under the field says which check the name leads to, and the warnings
// say what a pin does so nobody pins a port by accident.
export function SetServiceDialog({ port, host, options, isSaving, error, onCancel, onSave }: Props) {
  const [name, setName] = useState(port.service_name)
  const trimmed = name.trim().toLowerCase()
  const valid = SERVICE_NAME_RULE.test(trimmed)
  const unchanged = trimmed === port.service_name
  const monitored = port.state === 'MONITORED' || port.state === 'MISSING'
  const suggestions = options.filter((option) => option.protocols.includes(port.protocol))
  const listId = `service-options-${port.protocol}-${port.number}`

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Set service for ${portLabel(port)} on ${host}`}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
    >
      <div className="w-full max-w-md space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-xl">
        <h3 className="text-base font-semibold text-[var(--text)]">
          Set service for {portLabel(port)} on {host}
        </h3>

        <div>
          <label htmlFor={`${listId}-input`} className="mb-1 block text-xs text-[var(--text-muted)]">
            Service name
          </label>
          <input
            id={`${listId}-input`}
            aria-label="Service name"
            list={listId}
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            className="w-full rounded-lg border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2 font-mono text-sm text-[var(--text)] outline-none focus:border-[#ffb100]"
          />
          <datalist id={listId}>
            {suggestions.map((option) => (
              <option key={option.name} value={option.name}>
                {option.plugin}
              </option>
            ))}
          </datalist>
          {trimmed !== '' && !valid && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{SERVICE_NAME_HELP}</p>}
        </div>

        <p className="text-xs text-[var(--text-muted)]">
          Checked by:{' '}
          <span className="font-medium text-[var(--text)]">
            {valid ? checkedBy(trimmed, port.protocol, options) : '—'}
          </span>
        </p>

        <p className="text-xs text-[var(--text-muted)]">
          Scans will no longer change this port&apos;s service on this device. You can change it again or use Remove pin.
        </p>
        {monitored && (
          <p className="text-xs text-amber-600 dark:text-amber-400">
            Its Nagios service will be renamed (for example http-8080-tcp becomes ssh-8080-tcp). History stays under the old name.
          </p>
        )}
        {error && (
          <p role="alert" className="text-xs text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSaving}
            className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm text-[var(--text)] hover:bg-[var(--hover)] disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onSave(trimmed)}
            disabled={!valid || unchanged || isSaving}
            className="flex items-center gap-2 rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save
          </button>
        </div>
      </div>
    </div>
  )
}
