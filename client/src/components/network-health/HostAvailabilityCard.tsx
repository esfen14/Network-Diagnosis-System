import { Minus, TrendingDown, TrendingUp } from 'lucide-react'
import type { HostAvailability } from '../../types/networkHealth'
import { useDisplayTime } from '../../hooks/useDisplayTime'

type HostAvailabilityCardProps = {
  // GET /network-health/availability — null while loading or on error.
  data: HostAvailability | null
  error: string | null
}

function formatPoints(value: number) {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function TrendIcon({ value, className }: { value: number | null; className: string }) {
  if (value == null || value === 0) return <Minus className={className} />
  return value > 0 ? <TrendingUp className={className} /> : <TrendingDown className={className} />
}

export function HostAvailabilityCard({ data, error }: HostAvailabilityCardProps) {
  const { formatDate } = useDisplayTime()
  const pct = data?.availabilityPct ?? null

  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-[var(--text-muted)]">Host Availability</p>
          <div className="mt-1 flex items-center gap-2">
            <span className="text-3xl font-bold text-[#F4A90B]">
              {pct != null ? `${pct.toFixed(1)} %` : '—'}
            </span>
            {data?.changePct != null && (
              <span
                className="flex items-center gap-1 rounded bg-[#F4A90B] px-1.5 py-0.5 text-xs font-medium text-white"
                title="Latest day compared with the day before"
              >
                <TrendIcon value={data.changePct} className="h-3 w-3" />
                {formatPoints(data.changePct)}
              </span>
            )}
          </div>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#F4A90B]">
          <TrendIcon value={data?.trendPct ?? null} className="h-4 w-4 text-white" />
        </div>
      </div>

      {error ? (
        <p className="mt-6 flex h-24 items-center text-sm text-[var(--text-muted)]">{error}</p>
      ) : !data ? (
        <p className="mt-6 flex h-24 items-center text-sm text-[var(--text-muted)]">Loading…</p>
      ) : (
        <div className="mt-6 flex h-24 items-end gap-2" aria-label="Daily availability">
          {data.daily.map((day) => (
            <div
              key={day.start}
              title={`${formatDate(day.start)}: ${day.availabilityPct != null ? `${day.availabilityPct.toFixed(1)}%` : 'no data'}`}
              className={`flex-1 rounded-sm ${day.availabilityPct != null ? 'bg-[#F4A90B]' : 'bg-[var(--border)]'}`}
              style={{ height: `${Math.max(day.availabilityPct ?? 0, 4)}%` }}
            />
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between">
        <span className="flex items-center gap-1 rounded border border-[#F4A90B]/30 bg-[#F4A90B]/10 px-2 py-0.5 text-xs text-[#F4A90B]">
          <TrendIcon value={data?.trendPct ?? null} className="h-3 w-3" />
          {data?.trendPct != null ? formatPoints(data.trendPct) : 'No trend'}
        </span>
        <span className="text-xs text-[var(--text-muted)]">in last {data?.days ?? 7} days</span>
      </div>
    </div>
  )
}
