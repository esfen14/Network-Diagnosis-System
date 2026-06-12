import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'

const data = [
  { name: 'Healthy', value: 24, color: '#30D158' },
  { name: 'Warning', value: 6, color: '#F4A90B' },
  { name: 'Critical', value: 2, color: '#B91C2B' },
]

const legend = [
  { label: 'Healthy', count: '24 devices', color: 'bg-pinpoint-green' },
  { label: 'Warning', count: '6 devices', color: 'bg-[#F4A90B]' },
  { label: 'Critical', count: '2 devices', color: 'bg-red-700' },
]

export function DeviceHealthOverview() {
  return (
    <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center sm:justify-between">
      <div className="h-44 w-44">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={50}
              outerRadius={70}
              paddingAngle={2}
              dataKey="value"
              stroke="none"
            >
              {data.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="space-y-4">
        {legend.map((item) => (
          <div key={item.label} className="flex items-center gap-3">
            <span className={`h-2.5 w-2.5 rounded-full ${item.color}`} />
            <div>
              <p className="text-sm font-medium text-white">{item.label}</p>
              <p className="text-xs text-gray-400">{item.count}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
