import { Cpu, HardDrive, MemoryStick, MoreHorizontal } from 'lucide-react'

type ResourceUsageCardProps = {
  cpuPct: number | null
  memoryPct: number | null
  diskPct: number | null
  onClick?: () => void
}

function formatPct(value: number | null) {
  return value != null ? `${value}%` : '—'
}

export function ResourceUsageCard({ cpuPct, memoryPct, diskPct, onClick }: ResourceUsageCardProps) {
  const resources = [
    { label: 'Memory', value: formatPct(memoryPct), icon: MemoryStick },
    { label: 'CPU Usage', value: formatPct(cpuPct), icon: Cpu },
    { label: 'Disk', value: formatPct(diskPct), icon: HardDrive },
  ]

  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick() } : undefined}
      className={`flex h-full flex-col rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm ${onClick ? 'cursor-pointer transition hover:border-[var(--text-muted)]' : ''}`}
    >
      <div className="mb-5 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-[var(--text)]">Average Resource</h3>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]"
          aria-label="More options"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      <div className="grid flex-1 content-center gap-4 sm:grid-cols-3">
        {resources.map(({ label, value, icon: Icon }) => (
          <div key={label} className="flex flex-col items-center rounded-2xl bg-[var(--card-alt)] border border-[var(--border)] p-4">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#F4A90B]">
              <Icon className="h-5 w-5 text-white" />
            </div>
            <p className="whitespace-nowrap text-sm text-[var(--text-muted)]">{label}</p>
            <p className="mt-1 text-lg font-semibold text-[var(--text)]">{value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
