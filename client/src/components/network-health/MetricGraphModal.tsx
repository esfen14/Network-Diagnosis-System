import { useMemo, useState } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TrendPoint } from '../../types/dashboard'

export type GraphSeriesConfig = {
  key: string
  label: string
  color: string
  precision?: number
}

export type TrendHours = 1 | 6 | 24 | 168

const HOURS_OPTIONS: { value: TrendHours; label: string }[] = [
  { value: 1, label: 'Last hour' },
  { value: 6, label: 'Last 6 hours' },
  { value: 24, label: 'Last 24 hours' },
  { value: 168, label: 'Last 7 days' },
]

function formatBucketLabel(iso: string, hours: TrendHours) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return hours === 168
    ? d.toLocaleDateString(undefined, { weekday: 'short', hour: '2-digit' })
    : d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

export type MetricGraphModalProps = {
  title: string
  unit: string
  /** What this graph represents, e.g. "Ping RTA — network-wide average". */
  datasourceLabel: string
  series: GraphSeriesConfig[]
  /** One trend-point array per series key, straight from the trends API. */
  seriesData: Record<string, TrendPoint[]>
  hours: TrendHours
  onHoursChange: (hours: TrendHours) => void
  isLoading: boolean
  /** False when the backing plugin (e.g. NCPA) isn't deployed/enabled. */
  isConfigured: boolean
  emptyMessage?: string
  onClose: () => void
}

export function MetricGraphModal({
  title,
  unit,
  datasourceLabel,
  series,
  seriesData,
  hours,
  onHoursChange,
  isLoading,
  isConfigured,
  emptyMessage,
  onClose,
}: MetricGraphModalProps) {
  const [showRangePicker, setShowRangePicker] = useState(false)

  const chartData = useMemo(() => {
    const length = Math.max(0, ...series.map((s) => seriesData[s.key]?.length ?? 0))
    return Array.from({ length }, (_, i) => {
      const bucketStart = series.map((s) => seriesData[s.key]?.[i]?.bucketStart).find(Boolean)
      const row: Record<string, string | number | null> = {
        time: bucketStart ? formatBucketLabel(bucketStart, hours) : '',
      }
      series.forEach((s) => {
        row[s.key] = seriesData[s.key]?.[i]?.avgValue ?? null
      })
      return row
    })
  }, [series, seriesData, hours])

  const hasAnyData = series.some((s) => (seriesData[s.key] ?? []).some((p) => p.avgValue != null))

  const stats = useMemo(() => {
    return series.map((s) => {
      const values = (seriesData[s.key] ?? [])
        .map((p) => p.avgValue)
        .filter((v): v is number => v != null)
      const digits = s.precision ?? 1
      if (values.length === 0) {
        return { ...s, last: '—', max: '—', avg: '—' }
      }
      const last = values[values.length - 1]
      const max = Math.max(...values)
      const avg = values.reduce((a, b) => a + b, 0) / values.length
      return {
        ...s,
        last: last.toFixed(digits),
        max: max.toFixed(digits),
        avg: avg.toFixed(digits),
      }
    })
  }, [series, seriesData])

  const currentLabel = HOURS_OPTIONS.find((o) => o.value === hours)?.label ?? 'Last 24 hours'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="relative w-full max-w-3xl rounded-3xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-2xl">
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-5 top-5 text-[var(--text-muted)] hover:text-[var(--text)]"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="flex flex-wrap items-center justify-between gap-4 pr-8">
          <div className="flex items-baseline gap-3">
            <h2 className="text-lg font-semibold text-[#F4A90B]">{title}</h2>
            <span className="text-sm text-[var(--text-muted)]">{datasourceLabel}</span>
          </div>

          <div className="relative">
            <button
              type="button"
              onClick={() => setShowRangePicker((v) => !v)}
              className="flex items-center gap-1.5 rounded-xl bg-[var(--card-alt)] border border-[var(--border)] px-3 py-2 text-sm text-[var(--text)] hover:bg-[var(--hover)]"
            >
              {currentLabel} <ChevronDown className="h-3.5 w-3.5" />
            </button>
            {showRangePicker && (
              <div className="absolute right-0 top-full z-10 mt-2 w-40 rounded-xl border border-[var(--border)] bg-[var(--card)] p-1.5 shadow-lg">
                {HOURS_OPTIONS.map((o) => (
                  <button
                    key={o.value}
                    onClick={() => { onHoursChange(o.value); setShowRangePicker(false) }}
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
        </div>

        <div className="mt-4 h-72 w-full">
          {isLoading ? (
            <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
              Loading…
            </div>
          ) : !isConfigured || !hasAnyData ? (
            <div className="flex h-full flex-col items-center justify-center gap-1 px-8 text-center">
              <p className="text-sm font-medium text-[var(--text)]">No data available</p>
              <p className="text-sm text-[var(--text-muted)]">
                {emptyMessage ?? 'This metric has no data in the selected time window.'}
              </p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  {series.map((s) => (
                    <linearGradient key={s.key} id={`metric-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={s.color} stopOpacity={0.4} />
                      <stop offset="100%" stopColor={s.color} stopOpacity={0.05} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" />
                <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 11 }} />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'var(--chart-text)', fontSize: 11 }}
                  label={{ value: unit, angle: -90, position: 'insideLeft', fill: 'var(--chart-text)', fontSize: 11 }}
                />
                <Tooltip
                  contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 12, color: 'var(--tooltip-text)' }}
                  labelStyle={{ color: 'var(--tooltip-text)' }}
                />
                {series.map((s) => (
                  <Area
                    key={s.key}
                    type="monotone"
                    dataKey={s.key}
                    name={s.label}
                    stroke={s.color}
                    strokeWidth={2}
                    connectNulls
                    fill={`url(#metric-${s.key})`}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="mt-5 overflow-x-auto">
          <div className="flex min-w-full flex-col gap-2">
            {stats.map((s) => (
              <div key={s.key} className="flex flex-nowrap items-center gap-4 whitespace-nowrap text-sm">
                <span className="flex min-w-44 items-center gap-2 text-[var(--text)]">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: s.color }} />
                  {s.label}
                </span>
                <span className="flex flex-1 justify-between gap-6 sm:justify-end sm:gap-10">
                  <span className="text-[var(--text-muted)]">
                    <span className="font-medium text-[var(--text)]">{s.last}</span> last
                  </span>
                  <span className="text-[var(--text-muted)]">
                    <span className="font-medium text-[var(--text)]">{s.max}</span> max
                  </span>
                  <span className="text-[var(--text-muted)]">
                    <span className="font-medium text-[var(--text)]">{s.avg}</span> avg
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
