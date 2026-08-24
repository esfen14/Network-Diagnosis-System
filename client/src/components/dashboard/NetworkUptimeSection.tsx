import { MoreHorizontal } from 'lucide-react'
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

// 3 sample bars per month representing downtime hours logged that period
const data = months.flatMap((month) =>
  Array.from({ length: 3 }, (_, i) => ({
    label: `${month}-${i}`,
    month,
    hours: Math.round(Math.random() * 20 + 2),
  })),
)

export function NetworkUptimeSection() {
  return (
    <div className="rounded-3xl bg-[#1a1f26] p-6 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Network Uptime</h2>
        <button
          type="button"
          className="rounded-2xl bg-white/10 p-2 text-white/70 hover:bg-white/20"
          aria-label="More options"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <XAxis
              dataKey="month"
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
              interval={2}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
              domain={[0, 24]}
              ticks={[4, 8, 12, 16, 20, 24]}
            />
            <Tooltip
              contentStyle={{
                background: '#232323',
                border: 'none',
                borderRadius: 12,
                color: '#fff',
              }}
            />
            <Bar dataKey="hours" radius={[3, 3, 0, 0]}>
              {data.map((entry) => (
                <Cell
                  key={entry.label}
                  fill={entry.hours > 12 ? '#B91C2B' : '#E5E7EB'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}