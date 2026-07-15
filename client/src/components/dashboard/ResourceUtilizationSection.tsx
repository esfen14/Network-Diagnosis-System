import { useState } from 'react'
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

const monthlyData = [
  { month: 'Jan', cpu: 42 },
  { month: 'Feb', cpu: 55 },
  { month: 'Mar', cpu: 48 },
  { month: 'Apr', cpu: 62 },
  { month: 'May', cpu: 58 },
  { month: 'Jun', cpu: 47 },
]

const daysInMonth: Record<string, number> = {
  Jan: 31, Feb: 28, Mar: 31, Apr: 30, May: 31, Jun: 30,
}

// Generates a placeholder daily breakdown for the selected month.
// Swap this out for a real API call once daily CPU data is available from the backend.
function getDailyData(month: string) {
  const total = daysInMonth[month] ?? 30
  return Array.from({ length: total }, (_, i) => ({
    day: `${i + 1}`,
    cpu: Math.round(30 + Math.random() * 40),
  }))
}

const monthOptions = ['All', ...monthlyData.map((m) => m.month)]

export function ResourceUtilizationSection() {
  const [selectedMonth, setSelectedMonth] = useState('All')
  const [isOpen, setIsOpen] = useState(false)

  const chartData = selectedMonth === 'All' ? monthlyData : getDailyData(selectedMonth)
  const xKey = selectedMonth === 'All' ? 'month' : 'day'

  return (
    <div className="rounded-3xl bg-[#1a1f26] p-6 shadow-lg">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">
            Average Resource Utilization
          </h2>
          <p className="text-sm text-gray-400">
            CPU Usage{selectedMonth !== 'All' ? ` — ${selectedMonth}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsOpen((open) => !open)}
              className="flex items-center gap-1 rounded-2xl bg-white/10 px-3 py-2 text-sm text-white"
            >
              {selectedMonth}
              <ChevronDown className="h-4 w-4" />
            </button>
            {isOpen && (
              <div className="absolute right-0 z-10 mt-2 w-32 overflow-hidden rounded-2xl bg-[#232323] shadow-lg">
                {monthOptions.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => {
                      setSelectedMonth(option)
                      setIsOpen(false)
                    }}
                    className={`block w-full px-4 py-2 text-left text-sm hover:bg-white/10 ${
                      option === selectedMonth ? 'text-pinpoint-green' : 'text-white'
                    }`}
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            type="button"
            className="rounded-2xl bg-white/10 p-2 text-white/70"
            aria-label="More options"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="h-96 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#374151" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey={xKey}
              axisLine={false}
              tickLine={false}
              tick={{ fill: '#9CA3AF', fontSize: 12 }}
              interval={selectedMonth === 'All' ? 0 : 4}
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