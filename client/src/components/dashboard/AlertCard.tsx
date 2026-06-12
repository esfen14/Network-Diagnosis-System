type AlertCardProps = {
  severity: 'Critical' | 'High' | 'Medium'
  category: string
  message: string
  device: string
}

const severityStyles = {
  Critical: 'bg-red-600',
  High: 'bg-orange-500',
  Medium: 'bg-yellow-500',
}

export function AlertCard({ severity, category, message, device }: AlertCardProps) {
  return (
    <div className="rounded-3xl bg-pinpoint-card p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <span
          className={`rounded-3xl px-3 py-1 text-xs font-medium text-white ${severityStyles[severity]}`}
        >
          {severity}
        </span>
      </div>
      <p className="text-sm text-white/70">{category}</p>
      <p className="mt-1 text-sm text-white/70">{message}</p>
      <p className="mt-3 text-sm font-medium text-white">{device}</p>
    </div>
  )
}
