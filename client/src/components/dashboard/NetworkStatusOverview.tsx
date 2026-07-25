import { MoreHorizontal } from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'

const data = [
  { name: 'Up', value: 321, color: '#5AC8E8' },
  { name: 'Down', value: 66, color: '#B91C2B' },
]

export function NetworkStatusOverview() {
  return (
    <div className="flex h-full flex-col rounded-3xl bg-[#1a1f26] p-6 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Network Status Overview</h2>
        <button
          type="button"
          className="rounded-2xl bg-white/10 p-2 text-white/70 hover:bg-white/20"
          aria-label="More options"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      <div className="flex flex-1 items-center justify-center gap-8">
        <div className="h-48 w-48 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={62}
                outerRadius={98}
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
        <div className="space-y-5">
          {data.map((item) => (
            <div key={item.name} className="flex items-center gap-3">
              <span
                className="h-3.5 w-3.5 rounded-full"
                style={{ backgroundColor: item.color }}
              />
              <div>
                <p className="text-base font-medium text-white">{item.name}</p>
                <p className="text-sm text-gray-400">{item.value} devices</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}