import { useState } from 'react'
import { AlertTriangle, CheckCircle2, KeyRound, RotateCcw, Search, ServerCog } from 'lucide-react'
import type { NcpaDevice } from '../../types/ncpaDeployment'
import { AgentStatusBadge, OutcomeBadge } from './DeploymentBadges'

type Props = {
  devices: NcpaDevice[]
  isLoading: boolean
  isRunning: boolean
  selected: Set<number>
  onSelectedChange: (next: Set<number>) => void
  onDeploySelected: () => void
  onVerify: (deviceId: number) => void
  onRetry: (deviceId: number) => void
}

const BUTTON_SM =
  'inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-default disabled:opacity-50 dark:border-white/10 dark:text-gray-200 dark:hover:bg-white/10'

// "Devices" tab: every NCPA-eligible device with its host-key trust, agent
// state and last result. Pending and failed devices can be selected.
export function NcpaDevicesTable({
  devices,
  isLoading,
  isRunning,
  selected,
  onSelectedChange,
  onDeploySelected,
  onVerify,
  onRetry,
}: Props) {
  const [query, setQuery] = useState('')
  const q = query.trim().toLowerCase()
  const rows = devices.filter((d) => !q || d.hostname.toLowerCase().includes(q) || d.ipAddress.includes(q))
  const busyTitle = isRunning ? 'A deployment is already running.' : undefined

  const toggle = (id: number, on: boolean) => {
    const next = new Set(selected)
    if (on) next.add(id)
    else next.delete(id)
    onSelectedChange(next)
  }

  return (
    <section className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Devices</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            NCPA-eligible devices from the latest network scan. Select devices to deploy, or verify a host key first.
          </p>
        </div>
        <label className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
          <Search className="h-4 w-4 text-gray-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search devices"
            aria-label="Search devices"
            className="w-40 bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-500 dark:text-white"
          />
        </label>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-225 text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-500">
              <th className="w-10 px-4 py-3 font-normal"><span className="sr-only">Select</span></th>
              <th className="px-4 py-3 font-normal">Device</th>
              <th className="px-4 py-3 font-normal">IP Address</th>
              <th className="px-4 py-3 font-normal">Host Key</th>
              <th className="px-4 py-3 font-normal">Agent</th>
              <th className="px-4 py-3 font-normal">Last Result</th>
              <th className="px-4 py-3 font-normal"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && devices.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">Loading devices…</td>
              </tr>
            ) : devices.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                  <ServerCog className="mx-auto mb-2 h-5 w-5 opacity-60" />
                  No NCPA-eligible devices yet. Run a network scan to discover Linux hosts with SSH.
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">No devices match “{query}”.</td>
              </tr>
            ) : (
              rows.map((d) => (
                <tr
                  key={d.id}
                  className={`border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5 ${d.deployable ? '' : 'opacity-60'}`}
                >
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-[#ffb100]"
                      aria-label={`Select ${d.hostname}`}
                      checked={selected.has(d.id)}
                      disabled={!d.deployable || isRunning}
                      onChange={(e) => toggle(d.id, e.target.checked)}
                    />
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{d.hostname}</td>
                  <td className="px-4 py-3 tabular-nums text-gray-600 dark:text-gray-300">{d.ipAddress}</td>
                  <td className="px-4 py-3">
                    {d.trusted ? (
                      <span className="inline-flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400" title={d.fingerprint ? `SHA256:${d.fingerprint}` : undefined}>
                        <CheckCircle2 className="h-4 w-4" /> Trusted
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                        <AlertTriangle className="h-4 w-4" /> Not verified
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3"><AgentStatusBadge status={d.agentStatus} /></td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">
                    {!d.lastOutcome ? (
                      '—'
                    ) : d.lastOutcome === 'Success' ? (
                      <span className="text-emerald-600 dark:text-emerald-400">Deployed</span>
                    ) : (
                      <span className="inline-flex flex-wrap items-center gap-2">
                        <OutcomeBadge outcome={d.lastOutcome} />
                        {d.lastError && <span className="text-xs">{d.lastError}</span>}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {d.deployable && !d.trusted ? (
                      <button type="button" className={BUTTON_SM} disabled={isRunning} title={busyTitle} onClick={() => onVerify(d.id)}>
                        <KeyRound className="h-3.5 w-3.5" /> Verify
                      </button>
                    ) : d.agentStatus === 'Deployment Failed' ? (
                      <button type="button" className={BUTTON_SM} disabled={isRunning} title={busyTitle} onClick={() => onRetry(d.id)}>
                        <RotateCcw className="h-3.5 w-3.5" /> Retry
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
        <span className="tabular-nums">
          {selected.size > 0 ? `${selected.size} selected` : 'Deployed and incompatible devices cannot be selected.'}
        </span>
        <button
          type="button"
          onClick={onDeploySelected}
          disabled={selected.size === 0 || isRunning}
          title={busyTitle}
          className="inline-flex items-center gap-2 rounded-lg bg-[#ffb100] px-3 py-1.5 text-sm font-semibold text-gray-900 hover:bg-[#f0a500] disabled:cursor-default disabled:opacity-50"
        >
          <ServerCog className="h-4 w-4" /> Deploy selected
        </button>
      </div>
    </section>
  )
}
