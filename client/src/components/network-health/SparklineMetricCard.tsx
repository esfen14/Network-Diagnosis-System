import { MiniSparkline } from './MiniSparkline'

type SparklineMetricCardProps = {
  title: string; value: string; unit: string
  change: string; changeType: 'positive' | 'negative' | 'neutral'
  sparklineData: number[]; sparklineColor: string
  onClick?: () => void
}

export function SparklineMetricCard({ title, value, unit, change, changeType, sparklineData, sparklineColor, onClick }: SparklineMetricCardProps) {
  const badgeBg = changeType === 'positive' ? 'bg-emerald-500' : changeType === 'negative' ? 'bg-red-600' : 'bg-gray-400'
  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick() } : undefined}
      className={`flex h-[125px] flex-col gap-2 rounded-2xl bg-[var(--card)] border border-[var(--border)] p-4 shadow-sm ${onClick ? 'cursor-pointer transition hover:border-[var(--text-muted)]' : ''}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-[var(--text-muted)]">{title}</span>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium text-white ${badgeBg}`}>{change}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-xl font-bold text-[var(--text)]">{value}</span>
        <span className="text-xs text-[var(--text-muted)]">{unit}</span>
      </div>
      <MiniSparkline data={sparklineData} color={sparklineColor} gradientId={`spark-${title.replace(/\s/g, '')}`} />
    </div>
  )
}