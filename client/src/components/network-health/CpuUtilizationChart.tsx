import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { HostCpu } from '../../types/networkHealth'
import { formatBucketLabel } from '../../utils/formatBucketLabel'
import type { TrendHours } from './MetricGraphModal'
import { TimeRangeSelect } from './TimeRangeSelect'
import { useDisplayTime } from '../../hooks/useDisplayTime'

type CpuUtilizationChartProps = {
  // GET /network-health/cpu — null while loading or on error.
  data: HostCpu | null
  error: string | null
  hours: TrendHours
  onHoursChange: (hours: TrendHours) => void
  onHostChange: (hostname: string) => void
}

function formatPct(value: number | null) {
  return value != null ? `${value.toFixed(1)}%` : '—'
}

export function CpuUtilizationChart({ data, error, hours, onHoursChange, onHostChange }: CpuUtilizationChartProps) {
  const { timeZone } = useDisplayTime()
  const chartData = (data?.points ?? []).map((p) => ({
    time: formatBucketLabel(p.bucketStart, hours, timeZone),
    cpu: p.avgValue,
  }))
  const hasData = chartData.some((p) => p.cpu != null)

  let emptyMessage = 'No CPU data in the selected time window.'
  if (error) emptyMessage = error
  else if (!data) emptyMessage = 'Loading…'
  else if (data.hosts.length === 0) emptyMessage = 'No host has an NCPA CPU check yet. Deploy NCPA to see CPU utilization.'

  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm">
      <div className="mb-1 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-[var(--text)]">
            CPU Utilization{data?.hostname ? ` for ${data.hostname}` : ''}
          </h3>
          <p className="text-sm text-[var(--text-muted)]">Datasource: NCPA cpu/percent</p>
        </div>
        <div className="flex items-center gap-2">
        <TimeRangeSelect hours={hours} onChange={onHoursChange} />
        {data && data.hosts.length > 1 && (
          <select
            aria-label="Host"
            value={data.hostname ?? ''}
            onChange={(e) => onHostChange(e.target.value)}
            className="rounded-xl bg-[var(--card-alt)] border border-[var(--border)] px-3 py-2 text-sm text-[var(--text)] hover:bg-[var(--hover)]"
          >
            {data.hosts.map((host) => (
              <option key={host} value={host}>{host}</option>
            ))}
          </select>
        )}
        </div>
      </div>
      <p className="mb-4 text-sm text-[var(--text-muted)]">CPU Utilization (%)</p>
      <div className="h-56 w-full">
        {!hasData ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-[var(--text-muted)]">
            {emptyMessage}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="cpuGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#F4A90B" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#F4A90B" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 11 }} />
              <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 11 }} domain={[0, 100]} />
              <Tooltip contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 12, color: 'var(--tooltip-text)' }} labelStyle={{ color: 'var(--tooltip-text)' }} />
              <Area type="monotone" dataKey="cpu" name="CPU %" stroke="#F4A90B" strokeWidth={2} fill="url(#cpuGradient)" connectNulls />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-6 text-xs text-[var(--text-muted)]">
        <span><span className="text-[var(--text)]">{formatPct(data?.currentPct ?? null)}</span> current</span>
        <span><span className="text-[var(--text)]">{formatPct(data?.avgPct ?? null)}</span> avg</span>
        <span><span className="text-[var(--text)]">{formatPct(data?.maxPct ?? null)}</span> max</span>
      </div>
    </div>
  )
}
