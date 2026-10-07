import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TrendPoint } from '../../types/dashboard'
import { formatBucketLabel } from '../../utils/formatBucketLabel'
import type { TrendHours } from './MetricGraphModal'
import { TimeRangeSelect } from './TimeRangeSelect'
import { useDisplayTime } from '../../hooks/useDisplayTime'

const SERIES = [
  { key: 'load1', period: '1 min', color: '#0ea5e9' },
  { key: 'load5', period: '5 min', color: '#F4A90B' },
  { key: 'load15', period: '15 min', color: '#A78BFA' },
] as const

type LoadKey = (typeof SERIES)[number]['key']

type CpuLoadChartProps = {
  // Nagios server's check_load trend (GET /network-health/trends → nagios_server.cpu_load).
  load: { configured: boolean } & Record<LoadKey, TrendPoint[]>
  hours: TrendHours
  onHoursChange: (hours: TrendHours) => void
  isLoading: boolean
}

function loadStats(points: TrendPoint[]) {
  const values = points.map((p) => p.avgValue).filter((v): v is number => v != null)
  if (values.length === 0) return null
  return {
    last: values[values.length - 1],
    avg: values.reduce((a, b) => a + b, 0) / values.length,
    max: Math.max(...values),
  }
}

export function CpuLoadChart({ load, hours, onHoursChange, isLoading }: CpuLoadChartProps) {
  const { timeZone } = useDisplayTime()
  const length = Math.max(...SERIES.map((s) => load[s.key].length))
  const data = Array.from({ length }, (_, i) => {
    const bucketStart = SERIES.map((s) => load[s.key][i]?.bucketStart).find(Boolean)
    const row: Record<string, string | number | null> = {
      time: bucketStart ? formatBucketLabel(bucketStart, hours, timeZone) : '',
    }
    SERIES.forEach((s) => {
      row[s.key] = load[s.key][i]?.avgValue ?? null
    })
    return row
  })
  const hasData = SERIES.some((s) => load[s.key].some((p) => p.avgValue != null))

  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm">
      <div className="mb-1 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-[var(--text)]">CPU Load for Nagios server</h3>
          <p className="text-sm text-[var(--text-muted)]">Datasource: check_load (load1, load5, load15)</p>
        </div>
        <TimeRangeSelect hours={hours} onChange={onHoursChange} />
      </div>
      <div className="h-56 w-full">
        {!hasData ? (
          <div className="flex h-full items-center justify-center text-sm text-[var(--text-muted)]">
            {isLoading
              ? 'Loading…'
              : load.configured
                ? 'No CPU load data in the selected time window.'
                : 'check_load is not configured on the Nagios server.'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="loadGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#38BDF8" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#38BDF8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 11 }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 11 }} />
              <Tooltip contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 12, color: 'var(--tooltip-text)' }} />
              {SERIES.map((s, i) => (
                <Area
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={`Load (${s.period})`}
                  stroke={s.color}
                  strokeWidth={2}
                  fill={i === 0 ? 'url(#loadGradient)' : 'none'}
                  connectNulls
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="mt-4 grid grid-cols-3 gap-4 text-xs">
        {SERIES.map((s) => {
          const stats = loadStats(load[s.key])
          return (
            <div key={s.key} className="space-y-1">
              <p className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: s.color }} />
                {s.period}
              </p>
              <p className="text-[var(--text-muted)]"><span className="text-[var(--text)]">{stats ? stats.last.toFixed(2) : '—'}</span> last</p>
              <p className="text-[var(--text-muted)]"><span className="text-[var(--text)]">{stats ? stats.avg.toFixed(2) : '—'}</span> avg</p>
              <p className="text-[var(--text-muted)]"><span className="text-[var(--text)]">{stats ? stats.max.toFixed(2) : '—'}</span> max</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
