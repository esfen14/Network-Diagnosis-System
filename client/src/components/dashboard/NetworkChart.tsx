import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { TrendPoint } from '../../types/dashboard'

type NetworkChartProps = {
  data: TrendPoint[]
  isLoading: boolean
}

export function NetworkChart({ data, isLoading }: NetworkChartProps) {
  const points = data
    .filter((p) => p.avgValue != null)
    .map((p) => ({
      time: new Date(p.bucketStart).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }),
      value: p.avgValue,
    }))

  if (isLoading) {
    return <div className="flex h-64 w-full items-center justify-center text-sm text-[var(--text-muted)]">Loading…</div>
  }

  if (points.length === 0) {
    return <div className="flex h-64 w-full items-center justify-center text-sm text-[var(--text-muted)]">No latency data yet</div>
  }

  return (
    <div className="h-64 w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} />
          <Tooltip contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 12, color: 'var(--tooltip-text)' }} />
          <Area type="monotone" dataKey="value" stroke="#16a34a" strokeWidth={2} fill="url(#chartGradient)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
