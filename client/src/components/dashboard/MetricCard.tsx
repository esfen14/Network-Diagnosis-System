type MetricCardProps = {
  label: string
  value: string
  status: string
  statusColor?: string
}

export function MetricCard({ label, value, status, statusColor = 'text-emerald-600' }: MetricCardProps) {
  return (
    <div className="flex min-w-[117px] flex-col rounded-2xl bg-[var(--card-alt)] border border-[var(--border)] p-3">
      <span className="text-sm text-[var(--text-muted)]">{label}</span>
      <span className="mt-1 text-lg font-semibold text-[var(--text)]">{value}</span>
      <span className={`mt-2 text-xs font-medium ${statusColor}`}>{status}</span>
    </div>
  )
}
