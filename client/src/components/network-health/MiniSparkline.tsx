import { Area, AreaChart, ResponsiveContainer } from 'recharts'

type MiniSparklineProps = {
  data: number[]
  color: string
  gradientId: string
}

export function MiniSparkline({
  data,
  color,
  gradientId,
}: MiniSparklineProps) {
  const chartData = data.map((value, i) => ({ i, value }))

  return (
    <div className="h-4 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={chartData}
          margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient
              id={gradientId}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop
                offset="0%"
                stopColor={color}
                stopOpacity={0.4}
              />

              <stop
                offset="100%"
                stopColor={color}
                stopOpacity={0}
              />
            </linearGradient>
          </defs>

          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#${gradientId})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}