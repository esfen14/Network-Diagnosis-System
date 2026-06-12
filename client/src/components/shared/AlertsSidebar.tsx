import { Bug, Plug, User } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

type AlertItem = {
  title: string
  time: string
  icon: LucideIcon
  iconBg: string
}

const alerts: AlertItem[] = [
  { title: 'Alert 1', time: 'Just now', icon: Bug, iconBg: 'bg-gray-600' },
  { title: 'Alert 2', time: '2 minutes ago', icon: User, iconBg: 'bg-gray-600' },
  { title: 'Plugins loaded', time: '5 minutes ago', icon: Plug, iconBg: 'bg-blue-600' },
  { title: 'Network scan completed', time: '12 minutes ago', icon: Bug, iconBg: 'bg-emerald-600' },
  { title: 'Device SW02 unreachable', time: '1 hour ago', icon: User, iconBg: 'bg-red-600' },
]

export function AlertsSidebar() {
  return (
    <aside className="hidden w-72 shrink-0 border-l border-white/10 xl:block">
      <div className="sticky top-0 p-4">
        <h3 className="mb-4 text-sm font-semibold text-white">Alerts</h3>
        <div className="space-y-3">
          {alerts.map((alert) => (
            <div key={alert.title + alert.time} className="flex gap-3 rounded-xl p-2 hover:bg-white/5">
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${alert.iconBg}`}>
                <alert.icon className="h-4 w-4 text-white" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm text-white">{alert.title}</p>
                <p className="text-xs text-gray-500">{alert.time}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  )
}
