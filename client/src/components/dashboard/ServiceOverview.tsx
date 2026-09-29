import { useEffect, useState } from 'react'
import type { DashboardStatus, DashboardSummary } from '../../types/dashboard'
import type { PluginGroup } from '../../types/networkHealth'
import type { ServiceRow } from '../../types/service'
import { formatTimeAgo } from '../../utils/formatDateTime'

type StatusTone = 'green' | 'yellow' | 'red' | 'blue' | 'gray'

const toneStyles: Record<StatusTone, string> = {
  green: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  yellow: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  red: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  blue: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  gray: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

function Row({
  label,
  status,
  tone,
  title,
  pulse = false,
}: {
  label: string
  status: string
  tone: StatusTone
  title?: string
  pulse?: boolean
}) {
  return (
    <div title={title} className="flex items-center justify-between gap-2 rounded-xl px-2 py-2 hover:bg-[var(--hover)]">
      <span className="text-sm text-[var(--text)] truncate">{label}</span>
      <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${toneStyles[tone]} ${pulse ? 'animate-pulse' : ''}`}>
        {status}
      </span>
    </div>
  )
}

function SectionHeader({ label }: { label: string }) {
  return (
    <p className="pb-1 pt-3 text-xs font-medium uppercase text-[var(--text-muted)] first:pt-0">
      {label}
    </p>
  )
}

function serviceTone(state: ServiceRow['state']): StatusTone {
  switch (state) {
    case 'OK': return 'green'
    case 'WARNING': return 'yellow'
    case 'CRITICAL': return 'red'
    default: return 'gray'
  }
}

// Pinpoint polls Nagios every 60 seconds (server/app/scheduler.py), so a
// couple of missed polls is "stale" and several is "not updating".
const STALE_AFTER_MS = 3 * 60_000
const OUTDATED_AFTER_MS = 10 * 60_000

function freshnessTone(lastUpdate: Date | null, now: Date): StatusTone {
  if (!lastUpdate) return 'red'
  const age = now.getTime() - lastUpdate.getTime()
  if (age >= OUTDATED_AFTER_MS) return 'red'
  if (age >= STALE_AFTER_MS) return 'yellow'
  return 'green'
}

// On/Off row for a Nagios program-wide switch. `offTone` is how bad "Off" is.
function switchRow(label: string, enabled: boolean | null, offTone: StatusTone, offTitle: string) {
  if (enabled == null) return <Row key={label} label={label} status="Unknown" tone="gray" />
  return enabled
    ? <Row key={label} label={label} status="On" tone="green" />
    : <Row key={label} label={label} status="Off" tone={offTone} title={offTitle} />
}

const PLUGIN_STATE: Record<PluginGroup['worstState'], { tone: StatusTone; word: string }> = {
  critical: { tone: 'red', word: 'Critical' },
  warning: { tone: 'yellow', word: 'Warning' },
  unknown: { tone: 'gray', word: 'Unknown' },
  ok: { tone: 'green', word: 'OK' },
}

/** "3/3 OK", or the count in the worst state, e.g. "1 Critical". */
function pluginStatus(group: PluginGroup) {
  const { tone, word } = PLUGIN_STATE[group.worstState]
  const count = group.worstState === 'ok' ? `${group.ok}/${group.total}` : String(group[group.worstState])
  return { text: `${count} ${word}`, tone }
}

type ServiceOverviewProps = {
  status: DashboardStatus | null
  summary: DashboardSummary | null
  problemServices: ServiceRow[]
  // GET /network-health/plugins; null when it could not be loaded.
  pluginGroups: PluginGroup[] | null
  isLoading: boolean
}

export function ServiceOverview({ status, summary, problemServices, pluginGroups, isLoading }: ServiceOverviewProps) {
  const hasRealData = (summary?.hosts.total ?? 0) > 0 || (summary?.services.total ?? 0) > 0

  // Keeps "20s ago" and the freshness colour current between refreshes.
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 15_000)
    return () => window.clearInterval(id)
  }, [])

  const nagios = status?.nagios
  const lastUpdate = nagios?.lastStatusUpdate ? new Date(nagios.lastStatusUpdate) : null

  const hosts = summary?.hosts
  const services = summary?.services
  const attention = [
    { label: 'Unknown Services', count: services?.unknown ?? 0, tone: 'gray' as StatusTone },
    { label: 'Flapping Hosts', count: hosts?.flapping ?? 0, tone: 'yellow' as StatusTone, pulse: true },
    { label: 'Flapping Services', count: services?.flapping ?? 0, tone: 'yellow' as StatusTone, pulse: true },
    { label: 'Hosts in Downtime', count: hosts?.inDowntime ?? 0, tone: 'blue' as StatusTone },
    { label: 'Services in Downtime', count: services?.inDowntime ?? 0, tone: 'blue' as StatusTone },
  ]

  return (
    <aside className="hidden w-72 shrink-0 border-l border-[var(--border)] xl:block">
      <div className="sticky top-0 max-h-screen overflow-y-auto p-4">
        <h3 className="mb-4 text-sm font-semibold text-emerald-600">Service Overview</h3>

        {isLoading ? (
          <p className="text-sm text-[var(--text-muted)]">Loading…</p>
        ) : (
          <div className="space-y-1">
            <SectionHeader label="Monitoring System" />
            <Row
              label={nagios?.version ? `Nagios ${nagios.version}` : 'Nagios'}
              status={nagios?.running ? 'Running' : 'Not Running'}
              tone={nagios?.running ? 'green' : 'red'}
            />
            <Row
              label="Data Updated"
              status={lastUpdate ? formatTimeAgo(lastUpdate, now) : 'Never'}
              tone={freshnessTone(lastUpdate, now)}
              title={
                lastUpdate
                  ? `Pinpoint last read status from Nagios at ${lastUpdate.toLocaleString()}`
                  : 'Pinpoint has not read status from Nagios yet'
              }
            />
            {switchRow('Host Checks', nagios?.activeHostChecks ?? null, 'red', 'Nagios is not checking hosts — their states will not change.')}
            {switchRow('Service Checks', nagios?.activeServiceChecks ?? null, 'red', 'Nagios is not checking services — their states will not change.')}
            {switchRow('Notifications', nagios?.notificationsEnabled ?? null, 'red', 'Nagios will not send any alerts.')}
            {switchRow('Flap Detection', nagios?.flapDetectionEnabled ?? null, 'yellow', 'Hosts and services that keep changing state will not be flagged.')}

            {!hasRealData ? (
              <p className="mt-3 rounded-lg bg-[var(--card-alt)] px-2 py-2 text-xs text-[var(--text-muted)]">
                No hosts or services have been reported yet. Waiting for the first Nagios poll.
              </p>
            ) : (
              <>
                <SectionHeader label="Needs Attention" />
                {attention.map(({ label, count, tone, pulse }) => (
                  <Row
                    key={label}
                    label={label}
                    status={String(count)}
                    tone={count > 0 ? tone : 'gray'}
                    pulse={Boolean(pulse) && count > 0}
                  />
                ))}

                <SectionHeader label="Services by Type" />
                {pluginGroups == null ? (
                  <p className="px-2 py-2 text-sm text-[var(--text-muted)]">Unavailable</p>
                ) : pluginGroups.length === 0 ? (
                  <p className="px-2 py-2 text-sm text-[var(--text-muted)]">No services monitored yet</p>
                ) : (
                  pluginGroups.map((group) => {
                    const { text, tone } = pluginStatus(group)
                    return (
                      <Row
                        key={group.displayName}
                        label={group.displayName}
                        status={text}
                        tone={tone}
                        title={`${group.ok} OK · ${group.warning} warning · ${group.critical} critical · ${group.unknown} unknown`}
                      />
                    )
                  })
                )}

                <SectionHeader label="Services Needing Attention" />
                {problemServices.length === 0 ? (
                  <p className="px-2 py-2 text-sm text-[var(--text-muted)]">All services OK</p>
                ) : (
                  problemServices.map((svc) => (
                    <Row
                      key={`${svc.hostname}-${svc.service}`}
                      label={`${svc.hostname} / ${svc.service}`}
                      status={svc.state}
                      tone={serviceTone(svc.state)}
                      title={svc.pluginOutput}
                    />
                  ))
                )}
              </>
            )}
          </div>
        )}
      </div>
    </aside>
  )
}
