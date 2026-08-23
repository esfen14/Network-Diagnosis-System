import { useState } from 'react'
import { ChevronDown, MoreHorizontal } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const monthlyData = [
  { month: 'Jan', cpu: 42 }, { month: 'Feb', cpu: 55 }, { month: 'Mar', cpu: 48 },
  { month: 'Apr', cpu: 62 }, { month: 'May', cpu: 58 }, { month: 'Jun', cpu: 47 },
]

const daysInMonth: Record<string, number> = { Jan: 31, Feb: 28, Mar: 31, Apr: 30, May: 31, Jun: 30 }

function getDailyData(month: string) {
  const total = daysInMonth[month] ?? 30
  return Array.from({ length: total }, (_, i) => ({ day: `${i + 1}`, cpu: Math.round(30 + Math.random() * 40) }))
}

const monthOptions = ['All', ...monthlyData.map((m) => m.month)]

export function ResourceUtilizationSection() {
  const [selectedMonth, setSelectedMonth] = useState('All')
  const [isOpen, setIsOpen] = useState(false)

  const chartData = selectedMonth === 'All' ? monthlyData : getDailyData(selectedMonth)
  const xKey = selectedMonth === 'All' ? 'month' : 'day'

  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-[var(--text)]">Average Resource Utilization</h2>
          <p className="text-sm text-[var(--text-muted)]">CPU Usage{selectedMonth !== 'All' ? ` — ${selectedMonth}` : ''}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsOpen((o) => !o)}
              className="flex items-center gap-1 rounded-xl bg-[var(--card-alt)] border border-[var(--border)] px-3 py-2 text-sm text-[var(--text)] hover:bg-[var(--hover)]"
            >
              {selectedMonth}
              <ChevronDown className="h-4 w-4" />
            </button>
            {isOpen && (
              <div className="absolute right-0 z-10 mt-2 w-32 overflow-hidden rounded-xl bg-[var(--card)] border border-[var(--border)] shadow-lg">
                {monthOptions.map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => { setSelectedMonth(option); setIsOpen(false) }}
                    className={`block w-full px-4 py-2 text-left text-sm hover:bg-[var(--hover)] ${option === selectedMonth ? 'text-emerald-600 font-medium' : 'text-[var(--text)]'}`}
                  >
                    {option}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button type="button" className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]" aria-label="More options">
            <MoreHorizontal className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="h-96 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={xKey} axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} interval={selectedMonth === 'All' ? 0 : 4} />
            <YAxis axisLine={false} tickLine={false} tick={{ fill: 'var(--chart-text)', fontSize: 12 }} />
            <Tooltip contentStyle={{ background: 'var(--tooltip-bg)', border: '1px solid var(--tooltip-border)', borderRadius: 12, color: 'var(--tooltip-text)' }} />
            <Bar dataKey="cpu" fill="#16a34a" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
