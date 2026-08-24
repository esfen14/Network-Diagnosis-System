import { useState } from 'react'
import {
  Activity,
  FileText,
  FolderOpen,
  HelpCircle,
  LayoutDashboard,
  LogOut,
  Network,
  Settings,
  Users,
  Wrench,
} from 'lucide-react'
import { NavLink, useNavigate } from 'react-router-dom'

const navItems = [
  {
    to: '/dashboard',
    label: 'Overview',
    icon: LayoutDashboard,
    roles: ['network_admin', 'network_technician'],
  },
  {
    to: '/network-health',
    label: 'Network Health',
    icon: Activity,
    roles: ['network_admin', 'network_technician'],
  },
  {
    to: '/device-inventory',
    label: 'Device Inventory',
    icon: FolderOpen,
    roles: ['network_admin', 'network_technician'],
  },
  //{
    //to: '/topology',
    //label: 'Topology View',
    //icon: Network,
    //roles: ['network_admin', 'network_technician'],
  //},
  {
    to: '/plugins',
    label: 'Plugins',
    icon: Wrench,
    roles: ['network_admin', 'network_technician'],
  },
  {
    to: '/reports',
    label: 'Report',
    icon: FileText,
    roles: ['network_admin', 'network_technician'],
  },
  {
    to: '/system-logs',
    label: 'System Logs',
    icon: FileText,
    roles: ['network_admin'],
  },
  {
    to: '/accounts',
    label: 'Manage Accounts',
    icon: Users,
    roles: ['network_admin'],
  },
  {
    to: '/settings',
    label: 'Settings',
    icon: Settings,
    roles: ['network_admin'],
  },
]

export function Sidebar() {
  const navigate = useNavigate()
  const [showLogoutModal, setShowLogoutModal] = useState(false)

  const user = {
    role: 'network_admin',
  }

  const visibleItems = navItems.filter((item) =>
    item.roles.includes(user.role)
  )

  const handleLogout = () => {
    localStorage.clear()
    sessionStorage.clear()
    navigate('/login', { replace: true })
  }

  return (
    <>
      <aside className="fixed left-0 top-0 flex h-screen w-[220px] flex-col border-r border-gray-200 bg-white px-4 py-4">
        <div className="flex flex-1 flex-col">
          <div className="mb-6 flex items-center gap-2 px-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-pinpoint-btn">
              <Wrench className="h-4 w-4 text-gray-100" />
            </div>

            <span className="text-sm font-semibold text-black">
              PinPoint
            </span>
          </div>

          <div className="flex flex-col gap-1">
            {visibleItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-pinpoint-dark text-gray-100'
                      : 'text-black hover:bg-gray-200'
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
          <div className="group relative">
            <div className="flex cursor-pointer items-center gap-3 rounded-2xl px-3 py-2 transition hover:bg-gray-100">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gray-200">
                <Users className="h-4 w-4 text-gray-600" />
              </div>

              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-black">
                  {user.role === 'network_admin'
                    ? 'Network Admin'
                    : 'Network Technician'}
                </p>

                <p className="truncate text-xs text-gray-500">
                  admin@pinpoint.local
                </p>
              </div>
            </div>

            <div className="absolute bottom-full left-0 mb-2 hidden w-full rounded-xl border border-gray-200 bg-white py-1 shadow-lg group-hover:block">
              <button
                onClick={() => setShowLogoutModal(true)}
                className="flex w-full items-center gap-2 px-4 py-2 text-sm text-red-600 transition hover:bg-red-50"
              >
                <LogOut className="h-4 w-4" />
                Sign Out
              </button>
            </div>
          </div>
        </div>
      </aside>

      {showLogoutModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-3xl bg-white p-8 text-center shadow-xl">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#F4A90B]">
              <HelpCircle className="h-7 w-7 text-white" />
            </div>

            <h2 className="text-lg font-semibold text-gray-900">
              Sign out of PinPoint?
            </h2>

            <p className="mt-2 text-sm text-gray-500">
              Are you sure you want to sign out? You will need to log in again
              to access the system.
            </p>

            <div className="mt-6 flex justify-center gap-3">
              <button
                onClick={() => setShowLogoutModal(false)}
                className="rounded-2xl border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>

              <button
                onClick={handleLogout}
                className="rounded-2xl bg-red-600 px-5 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}