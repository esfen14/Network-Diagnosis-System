import type { DashboardStatus, DashboardSummary } from '../../types/dashboard'
import type { ServiceRow } from '../../types/service'

type StatusTone = 'green' | 'yellow' | 'red' | 'blue' | 'gray'

const toneStyles: Record<StatusTone, string> = {
  green: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  yellow: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  red: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  blue: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  gray: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

function Row({ label, status, tone }: { label: string; status: string; tone: StatusTone }) {
  return (
    <div className="flex items-center justify-between rounded-xl px-2 py-2 hover:bg-[var(--hover)]">
      <span className="text-sm text-[var(--text)] truncate">{label}</span>
      <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${toneStyles[tone]}`}>{status}</span>
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

// Original placeholder content, kept as a fallback for when the backend
// hasn't ingested any host/service data yet (a fresh environment with the
// Nagios poller not yet reachable) — an all-zero real panel reads as
// "broken", so show this illustrative version instead until there's
// something real to report.
type PlaceholderItem = { label: string; status: string; tone: StatusTone; isHeader?: boolean }

const placeholderServices: PlaceholderItem[] = [
  { label: 'System Status', status: 'Operational', tone: 'green' },
  { label: 'Monitoring Coverage', status: '', tone: 'gray', isHeader: true },
  { label: 'Network Devices', status: '321 Active', tone: 'blue' },
  { label: 'NRPE Agents', status: '295/321 Active', tone: 'blue' },
  { label: 'Network Health', status: '', tone: 'gray', isHeader: true },
  { label: 'HTTP', status: 'Ok', tone: 'green' },
  { label: 'DNS Server', status: 'Slow Response', tone: 'yellow' },
  { label: 'DHCP Server', status: 'Down', tone: 'red' },
  { label: 'Core Services', status: '', tone: 'gray', isHeader: true },
  { label: 'Nagios', status: 'Running', tone: 'green' },
  { label: 'Database', status: 'Healthy', tone: 'green' },
  { label: 'API Health', status: 'Responsive', tone: 'blue' },
  { label: 'Alerts & Notifications', status: '', tone: 'gray', isHeader: true },
  { label: 'Email Notification', status: 'Embedded', tone: 'blue' },
  { label: 'Alert Severity', status: 'Pending', tone: 'yellow' },
  { label: 'IMAP/POP', status: 'Operational', tone: 'green' },
  { label: 'Critical Alerts', status: '47 Alerts', tone: 'red' },
  { label: 'Warning Alerts', status: '90 Warnings', tone: 'yellow' },
  { label: 'Service Monitoring', status: '', tone: 'gray', isHeader: true },
  { label: 'FTP', status: 'Running', tone: 'green' },
]

type ServiceOverviewProps = {
  status: DashboardStatus | null
  summary: DashboardSummary | null
  problemServices: ServiceRow[]
  isLoading: boolean
}

export function ServiceOverview({ status, summary, problemServices, isLoading }: ServiceOverviewProps) {
  const hasRealData = (summary?.hosts.total ?? 0) > 0 || (summary?.services.total ?? 0) > 0

  return (
    <aside className="hidden w-72 shrink-0 border-l border-[var(--border)] xl:block">
      <div className="sticky top-0 max-h-screen overflow-y-auto p-4">
        <h3 className="mb-4 text-sm font-semibold text-emerald-600">Service Overview</h3>

        {isLoading ? (
          <p className="text-sm text-[var(--text-muted)]">Loading…</p>
        ) : !hasRealData ? (
          <div className="space-y-1">
            <p className="mb-2 rounded-lg bg-[var(--card-alt)] px-2 py-2 text-xs text-[var(--text-muted)]">
              No monitoring data yet — showing a preview of what this panel looks like once data comes in.
            </p>
            {placeholderServices.map((item) =>
              item.isHeader ? (
                <SectionHeader key={item.label} label={item.label} />
              ) : (
                <Row key={item.label} label={item.label} status={item.status} tone={item.tone} />
              )
            )}
          </div>
        ) : (
          <div className="space-y-1">
            <SectionHeader label="Monitoring System" />
            <Row
              label="Nagios"
              status={status?.nagios.running ? 'Running' : 'Not Running'}
              tone={status?.nagios.running ? 'green' : 'red'}
            />

            <SectionHeader label="Hosts" />
            <Row label="Total Hosts" status={String(summary?.hosts.total ?? 0)} tone="blue" />
            <Row label="Up" status={String(summary?.hosts.up ?? 0)} tone="green" />
            <Row
              label="Down / Unreachable"
              status={String((summary?.hosts.down ?? 0) + (summary?.hosts.unreachable ?? 0))}
              tone={(summary?.hosts.down ?? 0) + (summary?.hosts.unreachable ?? 0) > 0 ? 'red' : 'gray'}
            />

            <SectionHeader label="Services" />
            <Row label="Total Services" status={String(summary?.services.total ?? 0)} tone="blue" />
            <Row label="OK" status={String(summary?.services.ok ?? 0)} tone="green" />
            <Row label="Warning" status={String(summary?.services.warning ?? 0)} tone="yellow" />
            <Row label="Critical" status={String(summary?.services.critical ?? 0)} tone="red" />

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
                />
              ))
            )}
          </div>
        )}
      </div>
    </aside>
  )
}
