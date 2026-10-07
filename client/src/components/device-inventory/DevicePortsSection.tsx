import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'

import { errorMessage } from '../../lib/api'
import { changePort } from '../../lib/devicePortsApi'
import { useCurrentUser } from '../../contexts/CurrentUserContext'
import { useDevicePorts } from '../../hooks/useDevicePorts'
import type { DevicePort, PortStateName } from '../../types/devicePorts'
import { SetServiceDialog } from './SetServiceDialog'
import {
  ACTION_LABELS,
  type PortActionId,
  actionsFor,
  confirmationText,
  groupPorts,
  identifiedLabel,
  needsConfirmation,
  portLabel,
  relativeTime,
  requestFor,
} from './devicePortsLogic'
import { useDisplayTime } from '../../hooks/useDisplayTime'

type Props = {
  deviceId: number
  // The Nagios host name shown in confirmations.
  hostname: string
}

const STATE_STYLES: Record<PortStateName, string> = {
  MONITORED: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  MISSING: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  SUGGESTED: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  IGNORED: 'bg-gray-500/15 text-[var(--text-muted)]',
  ARCHIVED: 'bg-gray-500/10 text-[var(--text-muted)]',
}

const STATE_LABELS: Record<PortStateName, string> = {
  MONITORED: 'Monitored',
  MISSING: 'Missing',
  SUGGESTED: 'Suggested',
  IGNORED: 'Ignored',
  ARCHIVED: 'Archived',
}

const portKey = (port: Pick<DevicePort, 'protocol' | 'number'>) => `${port.protocol}/${port.number}`

type Confirm = { action: PortActionId; port: DevicePort }

// The Ports section of the device drawer (spec files/Device_Inventory_Requirements.md). It lists a
// device's ports in groups, says why each one is or is not monitored, and offers the actions of
// requirement §5 to users with system.hosts.edit. The server decides everything; after each action the
// list is loaded again.
export function DevicePortsSection({ deviceId, hostname }: Props) {
  const { hasPermission } = useCurrentUser()
  const canEdit = hasPermission('system.hosts.edit')
  const canViewPlugins = hasPermission('plugin.view')

  const { data, error, isLoading, reload } = useDevicePorts(deviceId)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<Confirm | null>(null)
  const [pinFor, setPinFor] = useState<DevicePort | null>(null)
  const [pinError, setPinError] = useState<string | null>(null)
  const [showArchived, setShowArchived] = useState(false)

  const device = data?.device
  const endedDevice = device?.state === 'RETIRED' || device?.state === 'MERGED'
  const editable = canEdit && !endedDevice

  // Sends one change, reloads, and reports a change that was saved but is not in Nagios yet.
  // Returns true when the server accepted it.
  async function send(port: DevicePort, action: PortActionId, serviceName?: string) {
    setBusyKey(portKey(port))
    setActionError(null)
    setNotice(null)
    try {
      const result = await changePort(deviceId, port.protocol, port.number, requestFor(action, serviceName))
      if (result.config_ok === false) {
        setNotice(`The change was saved but Nagios was not updated: ${result.config_message}`)
      }
      reload()
      return true
    } catch (err) {
      const message = errorMessage(err, 'Unable to change the port.')
      if (action === 'set_service') setPinError(message)
      else setActionError(message)
      return false
    } finally {
      setBusyKey(null)
    }
  }

  function choose(action: PortActionId, port: DevicePort) {
    if (action === 'set_service') {
      setPinError(null)
      setPinFor(port)
    } else if (needsConfirmation(action)) {
      setConfirm({ action, port })
    } else {
      void send(port, action)
    }
  }

  async function confirmAction() {
    if (!confirm) return
    const { action, port } = confirm
    setConfirm(null)
    await send(port, action)
  }

  async function savePin(serviceName: string) {
    if (!pinFor) return
    if (await send(pinFor, 'set_service', serviceName)) setPinFor(null)
  }

  const groups = data ? groupPorts(data.ports) : []

  return (
    <section>
      <h3 className="mb-2 font-semibold">Ports</h3>

      {isLoading && !data && (
        <p className="flex items-center text-[var(--text-muted)]">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading ports…
        </p>
      )}

      {error && (
        <div className="space-y-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-red-600 dark:text-red-400">
          <p>{error}</p>
          <button
            type="button"
            onClick={reload}
            className="rounded-lg border border-red-500/40 px-3 py-1 text-xs font-medium hover:bg-red-500/10"
          >
            Retry
          </button>
        </div>
      )}

      {data && data.ports.length === 0 && (
        <p className="text-[var(--text-muted)]">No ports discovered yet. Run a scan from Network Discovery.</p>
      )}

      {data && data.ports.length > 0 && (
        <p className="mb-2 text-xs text-[var(--text-muted)]">
          {STATE_ORDER.filter((state) => data.counts[state] > 0)
            .map((state) => `${data.counts[state]} ${STATE_LABELS[state].toLowerCase()}`)
            .join(' · ')}
        </p>
      )}

      {data && !canEdit && data.ports.length > 0 && (
        <p className="mb-2 text-xs text-[var(--text-muted)]">You can view ports but not change them.</p>
      )}
      {data && endedDevice && (
        <p className="mb-2 text-xs text-[var(--text-muted)]">
          This device is {device?.state === 'MERGED' ? 'merged' : 'retired'}.
        </p>
      )}

      {notice && (
        <p role="status" className="mb-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          {notice}
        </p>
      )}
      {actionError && (
        <p role="alert" className="mb-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {actionError}
        </p>
      )}

      <div className="space-y-4">
        {groups.map((group) => {
          const collapsed = group.id === 'archived' && !showArchived
          return (
            <div key={group.id}>
              {group.id === 'archived' ? (
                <button
                  type="button"
                  onClick={() => setShowArchived((open) => !open)}
                  aria-expanded={!collapsed}
                  className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]"
                >
                  {collapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                  {group.title} ({group.ports.length})
                </button>
              ) : (
                <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  {group.title} ({group.ports.length})
                </h4>
              )}

              {!collapsed && (
                <ul className="space-y-2">
                  {group.ports.map((port) => (
                    <PortRow
                      key={portKey(port)}
                      port={port}
                      host={hostname}
                      editable={editable}
                      canViewPlugins={canViewPlugins}
                      busy={busyKey === portKey(port)}
                      onAction={choose}
                    />
                  ))}
                </ul>
              )}
            </div>
          )
        })}
      </div>

      {confirm && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={`Confirm ${ACTION_LABELS[confirm.action]}`}
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4"
        >
          <div className="w-full max-w-sm space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 shadow-xl">
            <h3 className="text-base font-semibold text-[var(--text)]">{ACTION_LABELS[confirm.action]}</h3>
            <p className="text-sm text-[var(--text-muted)]">{confirmationText(confirm.action, confirm.port, hostname)}</p>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirm(null)}
                className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm text-[var(--text)] hover:bg-[var(--hover)]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmAction}
                className="rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black"
              >
                {ACTION_LABELS[confirm.action]}
              </button>
            </div>
          </div>
        </div>
      )}

      {pinFor && data && (
        <SetServiceDialog
          port={pinFor}
          host={hostname}
          options={data.service_options}
          isSaving={busyKey === portKey(pinFor)}
          error={pinError}
          onCancel={() => setPinFor(null)}
          onSave={savePin}
        />
      )}
    </section>
  )
}

const STATE_ORDER: PortStateName[] = ['MONITORED', 'MISSING', 'SUGGESTED', 'IGNORED', 'ARCHIVED']

type RowProps = {
  port: DevicePort
  host: string
  editable: boolean
  canViewPlugins: boolean
  busy: boolean
  onAction: (action: PortActionId, port: DevicePort) => void
}

function PortRow({ port, host, editable, canViewPlugins, busy, onAction }: RowProps) {
  const { formatDateTime } = useDisplayTime()
  const flagged = port.expected_service_name !== null && !port.mismatch_acknowledged
  const actions = editable ? actionsFor(port) : []

  return (
    <li className="rounded-xl border border-[var(--border)] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-semibold">{portLabel(port)}</span>
        <span>{port.service_name}</span>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATE_STYLES[port.state]}`}>
          {STATE_LABELS[port.state]}
        </span>
        {port.state === 'MISSING' && <span className="text-xs text-amber-600 dark:text-amber-400">not seen lately</span>}
        {flagged && (
          <span className="rounded-full bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400">
            Not used as intended
          </span>
        )}
        {port.promotion_held && (
          <span className="rounded-full bg-gray-500/15 px-2.5 py-0.5 text-xs font-medium text-[var(--text-muted)]">Held</span>
        )}
      </div>

      {flagged && (
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          found {port.service_name}, expected {port.expected_service_name}
        </p>
      )}

      <p className="mt-1 text-xs text-[var(--text-muted)]">
        {identifiedLabel(port)} · Check: {port.check_plugin ?? 'none'}
      </p>

      {port.reason && (
        <p className="mt-1 text-xs text-[var(--text)]">
          {port.reason.text}
          {(port.reason.code === 'plugin_not_enabled' || port.reason.code === 'monitoring_inactive') && canViewPlugins && port.check_plugin && (
            <>
              {' '}
              <Link to="/plugins" className="font-medium text-[#b37b00] underline dark:text-[#ffb100]">
                Enable {port.check_plugin}
              </Link>
            </>
          )}
        </p>
      )}

      {port.managed_by_ncpa && (
        <p className="mt-1 text-xs text-[var(--text-muted)]">Managed by NCPA deployment</p>
      )}

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-[var(--text-muted)]" title={port.last_seen_at ? formatDateTime(port.last_seen_at) : undefined}>
          Last seen {relativeTime(port.last_seen_at)}
        </span>
        {actions.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {actions.map((action) => (
              <button
                key={action}
                type="button"
                disabled={busy}
                onClick={() => onAction(action, port)}
                aria-label={`${ACTION_LABELS[action]} ${portLabel(port)} on ${host}`}
                className="rounded-lg border border-[var(--border)] px-2.5 py-1 text-xs font-medium text-[var(--text)] hover:bg-[var(--hover)] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {ACTION_LABELS[action]}
              </button>
            ))}
          </div>
        )}
      </div>
    </li>
  )
}
