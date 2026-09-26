import type { LucideIcon } from 'lucide-react'

type TrendStatCardProps = {
  title: string; value: string; change: string
  changeType: 'positive' | 'negative' | 'neutral'
  icon: LucideIcon; iconBg?: string
  onClick?: () => void
}

export function TrendStatCard({ title, value, change, changeType, icon: Icon, iconBg = 'bg-[var(--card-alt)]', onClick }: TrendStatCardProps) {
  const badgeBg = changeType === 'positive' ? 'bg-emerald-500' : changeType === 'negative' ? 'bg-red-600' : 'bg-gray-400'
  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick() } : undefined}
      className={`flex h-[125px] items-center justify-between gap-4 rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm ${onClick ? 'cursor-pointer transition hover:border-[var(--text-muted)]' : ''}`}
    >
      <div className="flex items-center gap-4">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${iconBg}`}>
          <Icon className="h-5 w-5 text-[var(--text-muted)]" />
        </div>
        <div>
          <p className="text-sm text-[var(--text-muted)]">{title}</p>
          <p className="text-2xl font-bold text-[var(--text)]">{value}</p>
        </div>
      </div>
      <div className="text-right">
        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium text-white ${badgeBg}`}>{change}</span>
        <p className="mt-1 text-xs text-[var(--text-muted)]">in last 7 Days</p>
      </div>
    </div>
  )
}
