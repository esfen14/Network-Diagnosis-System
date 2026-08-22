import { MiniSparkline } from './MiniSparkline'

type SparklineMetricCardProps = {
  title: string
  value: string
  unit: string
  change: string
  changeType: 'positive' | 'negative'
  sparklineData: number[]
  sparklineColor: string
}

export function SparklineMetricCard({
  title,
  value,
  unit,
  change,
  changeType,
  sparklineData,
  sparklineColor,
}: SparklineMetricCardProps) {
  const badgeBg = changeType === 'positive' ? 'bg-emerald-500' : 'bg-red-600'

  return (
    <div className="flex h-[125px] flex-col gap-2 rounded-3xl bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm text-white">{title}</span>

        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium text-white ${badgeBg}`}
        >
          {change}
        </span>
      </div>

      <div className="flex items-baseline gap-1">
        <span className="text-xl font-bold text-white">{value}</span>
        <span className="text-xs text-[#CACACA]">{unit}</span>
      </div>

      <MiniSparkline
        data={sparklineData}
        color={sparklineColor}
        gradientId={`spark-${title.replace(/\s/g, '')}`}
      />
    </div>
  )
}
