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
  { time: 'Sat 18:00', load: 1.9 },
  { time: 'Sat 21:00', load: 0.4 },
  { time: 'Sun 00:00', load: 2.0 },
  { time: 'Sun 03:00', load: 0.3 },
  { time: 'Sun 06:00', load: 1.85 },
  { time: 'Sun 09:00', load: 0.35 },
  { time: 'Sun 12:00', load: 1.95 },
  { time: 'Sun 15:00', load: 0.32 },
  { time: 'Sun 18:00', load: 1.9 },
]

const loadStats = [
  { label: 'Load average', period: '1 min', last: '0.33', avg: '0.34', max: '2.37' },
  { label: '', period: '15 min', last: '1.13', avg: '0.29', max: '1.27' },
]

export function CpuLoadChart() {
  return (
    <div className="rounded-3xl bg-white p-5 shadow-sm">
      <div className="mb-1 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-var(--system-text)">
            CPU Load for localhost
          </h3>
          <p className="text-sm text-var(--system-text-secondary)">Datasource: load1</p>
        </div>
      </div>

      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="loadGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#38BDF8" stopOpacity={0.5} />
                <stop offset="100%" stopColor="#38BDF8" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#E5E7EB" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="time"
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#6B7280', fontSize: 11 }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#6B7280', fontSize: 11 }}
              domain={[0, 2]}
            />
            <Tooltip
              contentStyle={{
                background: '#FFFFFF',
                border: '1px solid #E5E7EB',
                borderRadius: 12,
                color: '#111827',
              }}
            />
            <Area
              type="monotone"
              dataKey="load"
              stroke="#38BDF8"
              strokeWidth={2}
              fill="url(#loadGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-4 flex items-start gap-3">
        <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-sky-400" />
        <div className="grid grid-cols-2 gap-x-10 gap-y-1 text-xs">
          <span className="text-var(--system-text-secondary)">Load average</span>
          <span />
          {loadStats.map((stat) => (
            <span key={stat.period} className="col-span-2 -mt-1 text-sm font-medium text-var(--system-text)">
              {stat.period}
            </span>
          ))}
          <div className="col-span-2 grid grid-cols-2 gap-x-10">
            {loadStats.map((stat) => (
              <div key={`${stat.period}-detail`} className="space-y-1">
                <p className="text-gray-500">
                  <span className="text-var(--system-text)">{stat.last}</span> last
                </p>
                <p className="text-gray-500">
                  <span className="text-var(--system-text)">{stat.avg}</span> avg
                </p>
                <p className="text-gray-500">
                  <span className="text-var(--system-text)">{stat.max}</span> max
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}