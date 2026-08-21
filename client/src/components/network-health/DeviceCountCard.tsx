import type { LucideIcon } from 'lucide-react'

type DeviceCountCardProps = {
  title: string
  count: number
  icon: LucideIcon
  iconBg: string
}

export function DeviceCountCard({
  title,
  count,
  icon: Icon,
  iconBg,
}: DeviceCountCardProps) {
  return (
<<<<<<< HEAD
    <div className="flex h-[100px] items-center gap-4 rounded-3xl bg-[#171B20] p-5 shadow-sm">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-3xl ${iconBg}`}>
=======
    <div className="flex items-center gap-4 rounded-3xl bg-[var(--system-card)] p-5 shadow-sm">
      <div
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-3xl ${iconBg}`}
      >
>>>>>>> a4da439abc1fd13696322146175a2e97635e3d94
        <Icon className="h-5 w-5 text-white" />
      </div>

      <div>
        <p className="text-sm text-[var(--system-text-secondary)]">
          {title}
        </p>

        <p className="text-2xl font-bold text-[var(--system-text)]">
          {count}
        </p>
      </div>
    </div>
  )
}