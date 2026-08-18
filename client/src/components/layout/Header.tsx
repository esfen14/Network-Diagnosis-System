import { Bell, Clock, PanelLeft, Search, Star, UserCog } from 'lucide-react'
import { useLocation } from 'react-router-dom'

const pageTitles: Record<string, { section: string; page: string }> = {
  '/dashboard': { section: 'Dashboards', page: 'Overview' },
  '/network-health': { section: 'Network Health', page: 'Overview' },
  '/device-inventory': { section: 'Device Inventory', page: 'Overview' },
  '/topology': { section: 'Dashboards', page: 'Topology View' },
  '/plugins': { section: 'Dashboards', page: 'Plugins' },
  '/reports': { section: 'Dashboards', page: 'Reports' },
  '/system-logs': { section: 'Dashboards', page: 'System Logs' },
  '/accounts': { section: 'Dashboards', page: 'Manage Accounts' },
  '/settings': { section: 'Dashboards', page: 'Settings' },
}

export function Header() {
  const { pathname } = useLocation()

  const { section, page } = pageTitles[pathname] ?? {
    section: 'Dashboards',
    page: 'Overview',
  }

  return (
    <header className="flex items-center justify-between border-b border-black/10 px-4 py-4 dark:border-white/10">
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
          aria-label="Toggle sidebar"
        >
          <PanelLeft className="h-5 w-5" />
        </button>

        <button
          type="button"
          className="rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
          aria-label="Favorites"
        >
          <Star className="h-5 w-5" />
        </button>

        <nav className="ml-2 flex items-center gap-1 text-sm text-white-500 dark:text-white/50">
          <span className="text-gray-80 dark:text-whiite/50">
            {section}
          </span>

          <span>/</span>

          <span>{page}</span>
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 rounded-xl bg-black/5 px-3 py-2 dark:bg-white/10">
          <Search className="h-4 w-4 text-gray-400 dark:text-white/50" />

          <input
            type="search"
            placeholder="Search"
            className="w-40 bg-transparent text-sm text-gray-900 placeholder:text-gray-400 outline-none dark:text-white dark:placeholder:text-white/40"
          />

          <kbd className="rounded border border-black/10 px-1.5 py-0.5 text-xs text-gray-400 dark:border-white/20 dark:text-white/40">
            /
          </kbd>
        </div>

        <button
          type="button"
          className="rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
          aria-label="Notifications"
        >
          <Bell className="h-5 w-5" />
        </button>

        <button
          type="button"
          className="rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
          aria-label="History"
        >
          <Clock className="h-5 w-5" />
        </button>

        <button
          type="button"
          className="rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
          aria-label="Account settings"
        >
          <UserCog className="h-5 w-5" />
        </button>
      </div>
    </header>
  )
}