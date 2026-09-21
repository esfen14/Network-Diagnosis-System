import { MoreHorizontal } from 'lucide-react'
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
const data = months.flatMap((month) =>
  Array.from({ length: 3 }, (_, i) => ({ label: `${month}-${i}`, month, hours: Math.round(Math.random() * 20 + 2) }))
)

export function NetworkUptimeSection() {
  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--text)]">Network Uptime</h2>
        <button type="button" className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]" aria-label="More options">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      <div className="h-56 w-full min-w-0">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} interval={2} />
            <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} domain={[0, 24]} ticks={[4, 8, 12, 16, 20, 24]} />
            <Tooltip contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 12, color: 'var(--tooltip-text)' }} />
            <Bar dataKey="hours" radius={[3, 3, 0, 0]}>
              {data.map((entry) => <Cell key={entry.label} fill={entry.hours > 12 ? '#dc2626' : 'var(--chart-grid)'} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
