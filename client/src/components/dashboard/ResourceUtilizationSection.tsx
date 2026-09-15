import { useState } from 'react'
import { ChevronDown, MoreHorizontal } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TrendPoint } from '../../types/dashboard'

export type TrendHours = 1 | 6 | 24 | 168

const HOURS_OPTIONS: { value: TrendHours; label: string }[] = [
  { value: 1, label: 'Last hour' },
  { value: 6, label: 'Last 6 hours' },
  { value: 24, label: 'Last 24 hours' },
  { value: 168, label: 'Last 7 days' },
]

type ResourceUtilizationSectionProps = {
  cpuTrend: TrendPoint[]
  isLoading: boolean
  hours: TrendHours
  onHoursChange: (hours: TrendHours) => void
}

export function ResourceUtilizationSection({ cpuTrend, isLoading, hours, onHoursChange }: ResourceUtilizationSectionProps) {
  const [isOpen, setIsOpen] = useState(false)

  const chartData = cpuTrend
    .filter((p) => p.avgValue != null)
    .map((p) => ({
      time: new Date(p.bucketStart).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
      cpu: p.avgValue,
    }))

  const currentLabel = HOURS_OPTIONS.find((o) => o.value === hours)?.label ?? 'Last 24 hours'

  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-[var(--text)]">Average Resource Utilization</h2>
          <p className="text-sm text-[var(--text-muted)]">NCPA CPU Usage — {currentLabel}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsOpen((o) => !o)}
              className="flex items-center gap-1 rounded-xl bg-[var(--card-alt)] border border-[var(--border)] px-3 py-2 text-sm text-[var(--text)] hover:bg-[var(--hover)]"
            >
              {currentLabel}
              <ChevronDown className="h-4 w-4" />
            </button>
            {isOpen && (
              <div className="absolute right-0 z-10 mt-2 w-36 overflow-hidden rounded-xl bg-[var(--card)] border border-[var(--border)] shadow-lg">
                {HOURS_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => { onHoursChange(option.value); setIsOpen(false) }}
                    className={`block w-full px-4 py-2 text-left text-sm hover:bg-[var(--hover)] ${option.value === hours ? 'text-emerald-600 font-medium' : 'text-[var(--text)]'}`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button type="button" className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]" aria-label="More options">
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="h-96 w-full min-w-0">
        {isLoading ? (
          <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">Loading…</div>
        ) : chartData.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">No CPU data in this window</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} />
              <Tooltip contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 12, color: 'var(--tooltip-text)' }} />
              <Bar dataKey="cpu" fill="#16a34a" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
