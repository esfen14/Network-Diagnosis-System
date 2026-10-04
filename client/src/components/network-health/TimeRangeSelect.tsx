import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { TREND_HOURS_OPTIONS, type TrendHours } from '../../utils/trendHours'

type TimeRangeSelectProps = {
  hours: TrendHours
  onChange: (hours: TrendHours) => void
}

export function TimeRangeSelect({ hours, onChange }: TimeRangeSelectProps) {
  const [open, setOpen] = useState(false)
  const currentLabel = TREND_HOURS_OPTIONS.find((o) => o.value === hours)?.label ?? 'Last 24 hours'

  return (
    <div className="relative">
      <button
        type="button"
        aria-label="Time range"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded-xl bg-[var(--card-alt)] border border-[var(--border)] px-3 py-2 text-sm text-[var(--text)] hover:bg-[var(--hover)]"
      >
        {currentLabel} <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-10 mt-2 w-40 rounded-xl border border-[var(--border)] bg-[var(--card)] p-1.5 shadow-lg">
          {TREND_HOURS_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              onClick={() => { onChange(o.value); setOpen(false) }}
              className={`block w-full rounded-lg px-2.5 py-1.5 text-left text-sm ${
                o.value === hours ? 'bg-[#F4A90B]/15 text-[#F4A90B]' : 'text-[var(--text)] hover:bg-[var(--hover)]'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
