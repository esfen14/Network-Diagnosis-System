import type { ServiceStateLabel, SystemActivity } from '../../types/networkHealth'

type SystemActivityCardProps = {
  // GET /network-health/system-activity — null while loading or on error.
  data: SystemActivity | null
  error: string | null
}

const STATE_DISPLAY: Record<ServiceStateLabel, { label: string; dot: string }> = {
  ok: { label: 'Normal', dot: 'bg-emerald-500' },
  warning: { label: 'Warning', dot: 'bg-[#F4A90B]' },
  critical: { label: 'Critical', dot: 'bg-red-500' },
  unknown: { label: 'Unknown', dot: 'bg-gray-400' },
}

function perDevice(value: string, deviceCount: number) {
  return deviceCount === 1 ? value : `${value}/device`
}

export function SystemActivityCard({ data, error }: SystemActivityCardProps) {
  const processes = data?.processes ?? null
  const users = data?.users ?? null

  const rows: { label: string; value: string; dot?: string }[] = []
  if (processes) {
    rows.push(
      { label: 'Processes', value: perDevice(processes.avgPerDevice.toFixed(0), processes.deviceCount) },
      { label: 'Process Load', value: STATE_DISPLAY[processes.state].label, dot: STATE_DISPLAY[processes.state].dot },
      { label: 'Total Processes', value: `${processes.total.toLocaleString()} processes` },
      {
        label: 'Peak Processes (24h)',
        value: processes.peak24h ? `${processes.peak24h.count.toLocaleString()} on ${processes.peak24h.hostname}` : '—',
      },
    )
  }
  if (users) {
    const range = users.minPerDevice === users.maxPerDevice
      ? `${users.maxPerDevice}`
      : `${users.minPerDevice}-${users.maxPerDevice}`
    rows.push(
      { label: 'Users', value: perDevice(range, users.deviceCount) },
      {
        label: 'Session Change (1h)',
        value: users.change1h == null
          ? '—'
          : `${users.change1h > 0 ? '+' : ''}${users.change1h} ${Math.abs(users.change1h) === 1 ? 'user' : 'users'}`,
      },
    )
  }

  const deviceCount = Math.max(processes?.deviceCount ?? 0, users?.deviceCount ?? 0)

  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-[var(--text)]">System Activity</h3>
      </div>
      {error ? (
        <p className="py-2.5 text-sm text-[var(--text-muted)]">{error}</p>
      ) : !data ? (
        <p className="py-2.5 text-sm text-[var(--text-muted)]">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="py-2.5 text-sm text-[var(--text-muted)]">
          No process or user checks (check_procs, check_users) are configured yet.
        </p>
      ) : (
        <div>
          {rows.map(({ label, value, dot }) => (
            <div key={label} className="flex items-center justify-between border-b border-dashed border-[var(--border)] py-2.5 last:border-b-0">
              <span className="text-sm font-medium text-[#F4A90B]">{label}</span>
              <span className="flex items-center gap-1.5 text-sm text-[var(--text)]">
                {dot && <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />}
                {value}
              </span>
            </div>
          ))}
        </div>
      )}
      {rows.length > 0 && (
        <div className="mt-4 flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-[#F4A90B]" />
          <span className="text-xs text-[var(--text-muted)]">
            From {deviceCount === 1 ? '1 device' : `${deviceCount} devices`} with process/user checks
          </span>
        </div>
      )}
    </div>
  )
}
