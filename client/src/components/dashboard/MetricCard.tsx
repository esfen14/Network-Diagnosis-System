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
    <div className="flex min-w-[117px] flex-col rounded-3xl bg-gray-100 p-3">
      <span className="text-sm text-[var(--system-text-secondary)]">{label}</span>
      <span className="mt-1 text-lg font-semibold text-[var(--system-text)]">{value}</span>
      <span className={`mt-2 text-xs font-medium ${statusColor}`}>{status}</span>
    </div>
  )
}