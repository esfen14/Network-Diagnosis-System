import {
  Activity,
  FileText,
  FolderOpen,
  LayoutDashboard,
  Network,
  Settings,
  Users,
  Wrench,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/dashboard', label: 'Overview', icon: LayoutDashboard },
  { to: '/network-health', label: 'Network Health', icon: Activity },
  { to: '/device-inventory', label: 'Device Inventory', icon: FolderOpen },
  { to: '/topology', label: 'Topology View', icon: Network },
  { to: '/reports', label: 'Report', icon: FileText },
  { to: '/system-logs', label: 'System Logs', icon: FileText },
  { to: '/accounts', label: 'Manage Accounts', icon: Users },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 flex h-screen w-[220px] flex-col border-r border-gray-200 bg-white px-4 py-4">
      <div className="flex flex-1 flex-col">
        <div className="mb-6 flex items-center gap-2 px-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-pinpoint-btn">
            <Wrench className="h-4 w-4 text-white" />
          </div>

          <span className="text-sm font-semibold text-black">
            PinPoint
          </span>
        </div>

        <div className="flex flex-col gap-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-pinpoint-dark text-white'
                    : 'text-black hover:bg-gray-100'
                }`
              }
            >
              <Icon className="h-5 w-5 shrink-0" />
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      </div>

      <div className="mt-4 border-t border-gray-200 pt-4">
        <div className="flex items-center gap-3 rounded-2xl px-3 py-2 hover:bg-gray-100">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-200">
            <Users className="h-4 w-4 text-gray-600" />
          </div>

          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-black">
              Admin
            </p>
            <p className="truncate text-xs text-gray-500">
              admin@pinpoint.local
            </p>
          </div>
        </div>
      </div>
    </aside>
  )
}