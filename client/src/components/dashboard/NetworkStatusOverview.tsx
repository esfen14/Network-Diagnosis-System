import { MoreHorizontal } from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'

type NetworkStatusOverviewProps = {
  up: number
  down: number
  isLoading: boolean
}

export function NetworkStatusOverview({ up, down, isLoading }: NetworkStatusOverviewProps) {
  const data = [
    { name: 'Up', value: up, color: '#22C55E' },
    { name: 'Down', value: down, color: '#EF4444' },
  ]
  const hasData = up + down > 0

  return (
    <div className="flex h-full flex-col rounded-2xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--text)]">Network Status Overview</h2>
        <button type="button" className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]" aria-label="More options">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      {isLoading ? (
        <div className="flex flex-1 items-center justify-center text-sm text-[var(--text-muted)]">Loading…</div>
      ) : !hasData ? (
        <div className="flex flex-1 items-center justify-center text-sm text-[var(--text-muted)]">No host data yet</div>
      ) : (
        <div className="flex flex-1 flex-wrap items-center justify-center gap-6 sm:gap-8 min-w-0">
          <div className="h-48 w-48 shrink-0">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} cx="50%" cy="50%" innerRadius={62} outerRadius={98} paddingAngle={2} dataKey="value" stroke="none">
                  {data.map((entry) => <Cell key={entry.name} fill={entry.color} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-5">
            {data.map((item) => (
              <div key={item.name} className="flex items-center gap-3">
                <span className="h-3.5 w-3.5 rounded-full" style={{ backgroundColor: item.color }} />
                <div>
                  <p className="text-base font-medium text-[var(--text)]">{item.name}</p>
                  <p className="text-sm text-[var(--text-muted)]">{item.value} devices</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
