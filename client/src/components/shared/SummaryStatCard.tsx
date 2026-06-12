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
      className="rounded-3xl p-5 shadow-sm"
      style={{ background: gradient }}
    >
      <div className="flex items-start justify-between">
        <p className="text-sm text-white/90">{title}</p>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20">
          <Icon className="h-4 w-4 text-white" />
        </div>
      </div>
      <p className="mt-3 text-2xl font-semibold text-white">{value}</p>
      <p className="mt-1 text-sm text-white/80">{subtitle}</p>
    </div>
  )
}
