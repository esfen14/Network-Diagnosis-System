import { ChevronDown, MoreHorizontal } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const data = [
  { month: 'Jan', cpu: 42 },
  { month: 'Feb', cpu: 55 },
  { month: 'Mar', cpu: 48 },
  { month: 'Apr', cpu: 62 },
  { month: 'May', cpu: 58 },
  { month: 'Jun', cpu: 47 },
]

export function ResourceUtilizationSection() {
  return (
    <div className="rounded-3xl bg-[#1a1f26] p-6 shadow-lg">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">
            Average Resource Utilization
          </h2>
          <p className="text-sm text-gray-400">CPU Usage</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex items-center gap-1 rounded-2xl bg-white/10 px-3 py-2 text-sm text-white"
          >
            Month
            <ChevronDown className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="rounded-2xl bg-white/10 p-2 text-white/70"
            aria-label="More options"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#374151" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="month"
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
            />
            <Tooltip
              contentStyle={{
                background: '#232323',
                border: 'none',
                borderRadius: 12,
                color: '#fff',
              }}
            />
            <Bar dataKey="cpu" fill="#30D158" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
