import { MoreHorizontal } from 'lucide-react'

const rows = [
  { label: 'Processes',       value: '135/device' },
  { label: 'Users',           value: '2-4/device' },
  { label: 'Process Load',    value: 'Normal',    dot: 'bg-emerald-500' },
  { label: 'User Activity',   value: '310 processes' },
  { label: 'Peek Processes',  value: 'Moderate',  dot: 'bg-[#F4A90B]' },
  { label: 'Session Change',  value: '+2 users' },
]

export function SystemActivityCard() {
  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-[var(--text)]">System Activity</h3>
        <button type="button" className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]" aria-label="More options">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      <div>
        {rows.map(({ label, value, dot }) => (
          <div key={label} className="flex items-center justify-between border-b border-dashed border-[var(--border)] py-2.5 last:border-b-0">
            <span className="text-sm font-medium text-[#F4A90B]">{label}</span>
            <span className="flex items-center gap-1.5 text-sm text-[var(--text)]">
              {dot && <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />}
              {value}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-[#F4A90B]" />
        <span className="text-xs text-[var(--text-muted)]">Live monitoring active</span>
      </div>
    </div>
  )
}
