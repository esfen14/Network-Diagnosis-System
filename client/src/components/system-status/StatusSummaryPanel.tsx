type StatusItem = {
  label: string
  value: number
  color: string // tailwind bg class for the pill
}

type Props = {
  title: string
  items: StatusItem[]
}

export function StatusSummaryPanel({ title, items }: Props) {
  const total = items.reduce((sum, i) => sum + i.value, 0)
  const problems = items
    .filter((i) => i.label !== 'OK' && i.label !== 'Up' && i.label !== 'Pending')
    .reduce((sum, i) => sum + i.value, 0)

  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm dark:bg-[#171B20]">
      <h3 className="mb-4 text-sm font-medium text-gray-500 dark:text-gray-400">
        {title}
      </h3>

      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <div
            key={item.label}
            className="flex min-w-[76px] flex-1 flex-col items-center rounded-xl px-3 py-2.5"
            style={{ backgroundColor: item.color }}
          >
            <span className="text-lg font-semibold text-white">{item.value}</span>
            <span className="text-[11px] font-medium uppercase tracking-wide text-white/80">
              {item.label}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3 text-xs text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>{total} total</span>
        <span className={problems > 0 ? 'font-medium text-red-500' : ''}>
          {problems} {problems === 1 ? 'problem' : 'problems'}
        </span>
      </div>
    </div>
  )
}