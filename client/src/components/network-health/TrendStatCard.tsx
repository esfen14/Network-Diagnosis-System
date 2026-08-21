import type { LucideIcon } from 'lucide-react'

type TrendStatCardProps = {
  title: string
  value: string
  change: string
  changeType: 'positive' | 'negative' | 'neutral'
  icon: LucideIcon
  iconBg?: string
}

export function TrendStatCard({
  title,
  value,
  change,
  changeType,
  icon: Icon,
  iconBg = 'bg-white/10',
}: TrendStatCardProps) {
  const badgeBg =
    changeType === 'positive'
      ? 'bg-emerald-500'
      : changeType === 'negative'
        ? 'bg-red-600'
        : 'bg-gray-500'

  return (
    <div className="flex h-[125px] items-center justify-between gap-4 rounded-3xl bg-[#171B20] p-5 shadow-sm">
      <div className="flex items-center gap-4">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${iconBg}`}>
          <Icon className="h-5 w-5 text-white" />
        </div>
        <div>
          <p className="text-sm text-[#CACACA]">{title}</p>
          <p className="text-2xl font-bold text-white">{value}</p>
        </div>
      </div>
      <div className="text-right">
        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium text-white ${badgeBg}`}>
          {change}
        </span>
        <p className="mt-1 text-xs text-[#CACACA]">in last 7 Days</p>
      </div>
    </div>
  )
}