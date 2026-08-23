import type { LucideIcon } from 'lucide-react'

type DeviceCountCardProps = {
  title: string; count: number; icon: LucideIcon; iconBg: string
}

export function DeviceCountCard({ title, count, icon: Icon, iconBg }: DeviceCountCardProps) {
  return (
    <div className="flex items-center gap-4 rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${iconBg}`}>
        <Icon className="h-5 w-5 text-white" />
      </div>
      <div>
        <p className="text-sm text-[var(--text-muted)]">{title}</p>
        <p className="text-2xl font-bold text-[var(--text)]">{count}</p>
      </div>
    </div>
  )
}
