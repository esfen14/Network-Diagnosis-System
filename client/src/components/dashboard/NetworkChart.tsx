import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const data = [
  { hour: '0h', value: 72 },
  { hour: '4h', value: 85 },
  { hour: '8h', value: 78 },
  { hour: '12h', value: 92 },
  { hour: '16h', value: 88 },
  { hour: '20h', value: 95 },
  { hour: '24h', value: 91 },
]

export function NetworkChart() {
  return (
    <div className="h-64 w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="hour" axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} />
          <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} domain={[0, 100]} />
          <Tooltip contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 12, color: 'var(--tooltip-text)' }} />
          <Area type="monotone" dataKey="value" stroke="#16a34a" strokeWidth={2} fill="url(#chartGradient)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
