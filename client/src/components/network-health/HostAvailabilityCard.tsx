import { TrendingDown } from 'lucide-react'

const barHeights = [40, 65, 55, 80, 70, 45, 60]

export function HostAvailabilityCard() {
  return (
    <div className="rounded-3xl bg-var(--system-card) p-5 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-var(--system-text-secondary)">
            Host Availability
          </p>

          <div className="mt-1 flex items-center gap-2">
            <span className="text-3xl font-bold text-[#F4A90B]">
              87.1 %
            </span>

            <span className="flex items-center gap-1 rounded bg-[#F4A90B] px-1.5 py-0.5 text-xs font-medium text-white">
              <TrendingDown className="h-3 w-3" />
              -12.2%
            </span>
          </div>
        </div>

        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#F4A90B]">
          <TrendingDown className="h-4 w-4 text-white" />
        </div>
      </div>

      <div className="mt-6 flex h-24 items-end gap-2">
        {barHeights.map((h, i) => (
          <div
            key={i}
            className="flex-1 rounded-sm bg-[#F4A90B]"
            style={{ height: `${h}%` }}
          />
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <span className="flex items-center gap-1 rounded border border-[#F4A90B]/30 bg-[#F4A90B]/10 px-2 py-0.5 text-xs text-[#F4A90B]">
          <TrendingDown className="h-3 w-3" />
          7.5%
        </span>

        <span className="text-xs text-var(--system-text-secondary)">
          in last 7 Days
        </span>
      </div>
    </div>
  )
}