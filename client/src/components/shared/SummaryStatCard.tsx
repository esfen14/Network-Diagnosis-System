import type { LucideIcon } from 'lucide-react'

type SummaryStatCardProps = {
  title: string
  value: string
  subtitle: string
  icon: LucideIcon
  gradient: string
}

export function SummaryStatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  gradient,
}: SummaryStatCardProps) {
  return (
    <div
      className="rounded-3xl p-[var(--dash-stat-padding)] shadow-sm"
      style={{ background: gradient }}
    >
      <div className="flex items-start justify-between">
        {/* Use inline style to guarantee white regardless of any CSS variable overrides */}
        <p className="text-sm" style={{ color: 'rgba(255,255,255,0.9)' }}>{title}</p>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20">
          <Icon className="h-4 w-4" style={{ color: '#ffffff' }} />
        </div>
      </div>
      <p className="mt-3 text-2xl font-semibold" style={{ color: '#ffffff' }}>{value}</p>
      <p className="mt-1 text-sm" style={{ color: 'rgba(255,255,255,0.8)' }}>{subtitle}</p>
    </div>
  )
}
