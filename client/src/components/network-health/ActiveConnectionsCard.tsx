import type { ConnectionCounts } from '../../types/networkHealth'

type ActiveConnectionsCardProps = {
  // GET /network-health/connections — TCP sockets on the Nagios server.
  data: ConnectionCounts | null
  error: string | null
}

export function ActiveConnectionsCard({ data, error }: ActiveConnectionsCardProps) {
  const breakdown = data?.available
    ? [
        { label: 'Listening', value: data.listening },
        { label: 'Time wait', value: data.timeWait },
        { label: 'Other', value: data.other },
      ]
    : []

  let note: string | null = null
  if (error) note = error
  else if (!data) note = 'Loading…'
  else if (!data.available) note = 'Connection counts are only available when Pinpoint runs on Linux.'

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm">
      <span className="text-sm text-[var(--text-muted)]">Active Connections</span>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-bold text-[var(--text)]">
          {data?.available && data.established != null ? data.established.toLocaleString() : '—'}
        </span>
        <span className="text-sm text-[var(--text-muted)]">established</span>
      </div>
      {note ? (
        <p className="text-xs text-[var(--text-muted)]">{note}</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 text-xs">
            {breakdown.map(({ label, value }) => (
              <div key={label}>
                <p className="text-[var(--text-muted)]">{label}</p>
                <p className="font-medium text-[var(--text)]">{value ?? '—'}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-[var(--text-muted)]">TCP connections on the Nagios server ({data?.hostname})</p>
        </>
      )}
    </div>
  )
}
