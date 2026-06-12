type MetricCardProps = {
  label: string
  value: string
  status: string
  statusColor?: string
}

export function MetricCard({
  label,
  value,
  status,
  statusColor = 'text-pinpoint-green',
}: MetricCardProps) {
  return (
    <div className="flex min-w-[117px] flex-col rounded-3xl bg-pinpoint-card p-3">
      <span className="text-sm text-pinpoint-gray-300">{label}</span>
      <span className="mt-1 text-lg font-semibold text-white">{value}</span>
      <span className={`mt-2 text-xs font-medium ${statusColor}`}>{status}</span>
    </div>
  )
}
