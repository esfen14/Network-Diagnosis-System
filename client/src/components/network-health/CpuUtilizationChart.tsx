import { ChevronDown, MoreHorizontal } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const data = [
  { time: 'Sat 18:00', cpu: 35 },
  { time: 'Sun 00:00', cpu: 42 },
  { time: 'Sun 06:00', cpu: 58 },
  { time: 'Sun 12:00', cpu: 72 },
  { time: 'Sun 18:00', cpu: 65 },
]

const categories = ['Idle', 'System', 'User', 'Wait', 'Utilization']

export function CpuUtilizationChart() {
  return (
    <div className="rounded-3xl bg-var(--system-card) p-5 shadow-sm">
      <div className="mb-1 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-var(--system-text)">
            CPU Utilization for localhost
          </h3>

          <p className="text-sm text-var(--system-text-secondary)">
            Datasource: user
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="flex items-center gap-1 rounded-2xl bg-var(--system-input) px-3 py-2 text-sm text-var(--system-text) transition hover:opacity-80"
          >
            24 hours
            <ChevronDown className="h-4 w-4" />
          </button>

          <button
            type="button"
            className="rounded-2xl bg-var(--system-input) p-2 text-var(--system-text-secondary) transition hover:opacity-80"
            aria-label="More options"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>

      <p className="mb-4 text-sm text-var(--system-text-secondary)">
        CPU Utilization (%)
      </p>

      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{
              top: 8,
              right: 8,
              left: 0,
              bottom: 0,
            }}
          >
            <defs>
              <linearGradient
                id="cpuGradient"
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop
                  offset="0%"
                  stopColor="#F4A90B"
                  stopOpacity={0.4}
                />

                <stop
                  offset="100%"
                  stopColor="#F4A90B"
                  stopOpacity={0}
                />
              </linearGradient>
            </defs>

            <CartesianGrid
              stroke="var(--system-chart-grid)"
              strokeDasharray="3 3"
              vertical={false}
            />

            <XAxis
              dataKey="time"
              axisLine={false}
              tickLine={false}
              tick={{
                fill: 'var(--system-chart-text)',
                fontSize: 11,
              }}
            />

            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{
                fill: 'var(--system-chart-text)',
                fontSize: 11,
              }}
              domain={[0, 80]}
            />

            <Tooltip
              contentStyle={{
                background: 'var(--system-tooltip-bg)',
                border: '1px solid var(--system-tooltip-border)',
                borderRadius: 12,
                color: 'var(--system-text)',
              }}
              labelStyle={{
                color: 'var(--system-text)',
              }}
            />

            <Area
              type="monotone"
              dataKey="cpu"
              stroke="#F4A90B"
              strokeWidth={2}
              fill="url(#cpuGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 flex flex-wrap gap-4">
        {categories.map((cat) => (
          <span
            key={cat}
            className="text-xs text-var(--system-text-secondary)"
          >
            {cat}
          </span>
        ))}
      </div>
    </div>
  )
}