import { useEffect, useRef, useState } from 'react'
import { Bell, Clock, HelpCircle, LogOut, PanelLeft, Settings, Star, Trash2, UserCog } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'

const pageTitles: Record<string, { section: string; page: string }> = {
  '/dashboard': { section: 'Dashboards', page: 'Overview' },
  '/network-health': { section: 'Network Health', page: 'Overview' },
  '/device-inventory': { section: 'Host Inventory', page: 'Overview' },
  '/topology': { section: 'System Status', page: 'All Hosts' },
  '/plugins': { section: 'Plugins', page: 'System Plugins' },
  '/reports': { section: 'Reports', page: 'System Reports' },
  '/system-logs': { section: 'System Logs', page: 'All' },
  '/accounts': { section: 'Management', page: 'Manage Accounts' },
  '/settings': { section: 'Management', page: 'Settings' },
}

const FAVORITES_KEY = 'nds:favorites'
const HISTORY_KEY = 'nds:history'
const MAX_HISTORY = 15

type NotificationItem = {
  id: string
  title: string
  detail: string
  time: string
  read: boolean
}

type HistoryEntry = {
  path: string
  visitedAt: number
}

// abang - dummy lang muna to, palitan pag live na yung /api/notifications
const seedNotifications: NotificationItem[] = [
  { id: '1', title: 'Device offline', detail: 'SW-CORE-02 stopped responding', time: '5m ago', read: false },
  { id: '2', title: 'Plugin installed', detail: 'SNMP Monitor v2 added', time: '1h ago', read: false },
  { id: '3', title: 'Report ready', detail: 'Link Health report finished generating', time: 'Yesterday', read: true },
]

function useOutsideClick(onOutside: () => void) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onOutside()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onOutside])

  return ref
}

// para readable yung timestamp sa History dropdown, e.g. "Just now", "12m ago", "Yesterday"
function formatRelativeTime(timestamp: number) {
  const diffMs = Date.now() - timestamp
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return new Date(timestamp).toLocaleDateString()
}

// pag naiwan yung lumang data (yung dati stringsAra lang na array, wala pang timestamp)
function loadHistory(): HistoryEntry[] {
  try {
    const raw = JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]')
    if (!Array.isArray(raw)) return []

    return raw.filter(
      (entry): entry is HistoryEntry =>
        entry &&
        typeof entry === 'object' &&
        typeof entry.path === 'string' &&
        typeof entry.visitedAt === 'number' &&
        !Number.isNaN(entry.visitedAt)
    )
  } catch {
    return []
  }
}

export function Header() {
  const { pathname } = useLocation()
  const navigate = useNavigate()

  const { section, page } = pageTitles[pathname] ?? {
    section: 'Dashboards',
    page: 'Overview',
  }

  const [favorites, setFavorites] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem(FAVORITES_KEY) ?? '[]')
    } catch {
      return []
    }
  })
  const isFavorited = favorites.includes(pathname)

  const [history, setHistory] = useState<HistoryEntry[]>(loadHistory)

  const [notifications, setNotifications] = useState<NotificationItem[]>(seedNotifications)
  const unreadCount = notifications.filter((n) => !n.read).length

  const [openMenu, setOpenMenu] = useState<'notifications' | 'history' | 'account' | null>(null)
  const menuRef = useOutsideClick(() => setOpenMenu(null))

  const [showLogoutModal, setShowLogoutModal] = useState(false)

  // esc para isara lahat ng dropdown
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpenMenu(null)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // log every actual page visit dito, may timestamp na para di na basta list lang ng paths
  // ayaw natin i-log ulit kung same page lang paulit ulit (avoid spam sa list)
  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setHistory((prev) => {
        if (prev[0]?.path === pathname) return prev

        const next = [
          { path: pathname, visitedAt: Date.now() },
          ...prev.filter((entry) => entry.path !== pathname),
        ].slice(0, MAX_HISTORY)

        localStorage.setItem(HISTORY_KEY, JSON.stringify(next))
        return next
      })
    }, 0)

    return () => window.clearTimeout(timeoutId)
  }, [pathname])

  const clearHistory = () => {
    setHistory([])
    localStorage.removeItem(HISTORY_KEY)
  }

  const toggleFavorite = () => {
    setFavorites((prev) => {
      const next = isFavorited ? prev.filter((p) => p !== pathname) : [...prev, pathname]
      localStorage.setItem(FAVORITES_KEY, JSON.stringify(next))
      return next
    })
  }

  const markAllRead = () => {
    // abang - dapat PATCH sa backend to pag connected na
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })))
  }

  const handleLogout = async () => {
    try {
      await fetch('/api/user/logout', {
        method: 'POST',
        credentials: 'include',
      })
    } catch (error) {
      console.error('Logout request failed:', error)
    }

    localStorage.clear()
    sessionStorage.clear()
    navigate('/login', { replace: true })
  }

  const toggleMenu = (menu: 'notifications' | 'history' | 'account') => {
  setOpenMenu((prev) => (prev === menu ? null : menu))
}
  return (
    <header className="relative flex items-center justify-between border-b border-black/10 px-4 py-4 dark:border-white/10">
      <div className="flex items-center gap-2">
        <button
          type="button"
          // abang - pansamantala lang to, dapat kasabay ng state ng actual Sidebar
          // pag may time, ilipat na lang natin sa context para di na event-based
          onClick={() => window.dispatchEvent(new CustomEvent('nds:toggle-sidebar'))}
          className="rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
          aria-label="Toggle sidebar"
        >
          <PanelLeft className="h-5 w-5" />
        </button>

        <button
          type="button"
          onClick={toggleFavorite}
          aria-pressed={isFavorited}
          className={`rounded-2xl p-2 transition hover:bg-black/5 dark:hover:bg-white/10 ${
            isFavorited
              ? 'text-[#ffb100]'
              : 'text-gray-500 hover:text-gray-900 dark:text-white/70 dark:hover:text-white'
          }`}
          aria-label="Favorites"
        >
          <Star className="h-5 w-5" fill={isFavorited ? 'currentColor' : 'none'} />
        </button>

        <nav className="ml-2 flex items-center gap-1 text-sm text-white-500 dark:text-white/50">
          <span className="text-gray-80 dark:text-whiite/50">
            {section}
          </span>

          <span>/</span>

          <span>{page}</span>
        </nav>
      </div>

      <div className="flex items-center gap-3" ref={menuRef}>
        {/* Notifications */}
        <div className="relative">
          <button
            type="button"
            onClick={() => toggleMenu('notifications')}
            className="relative rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
            aria-label="Notifications"
          >
            <Bell className="h-5 w-5" />
            {unreadCount > 0 && (
              <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-medium text-white">
                {unreadCount}
              </span>
            )}
          </button>

          {openMenu === 'notifications' && (
            <div className="absolute right-0 top-full z-20 mt-2 w-80 rounded-xl border border-gray-200 bg-white shadow-lg dark:border-white/10 dark:bg-[#171B20]">
              <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-white/10">
                <span className="text-sm font-medium text-gray-900 dark:text-white">Notifications</span>
                {unreadCount > 0 && (
                  <button
                    onClick={markAllRead}
                    className="text-xs font-medium text-[#ffb100] hover:underline"
                  >
                    Mark all read
                  </button>
                )}
              </div>

              <div className="max-h-72 overflow-y-auto">
                {notifications.length === 0 ? (
                  <p className="px-4 py-6 text-center text-sm text-gray-400">No notifications</p>
                ) : (
                  notifications.map((n) => (
                    <div
                      key={n.id}
                      className={`border-b border-gray-50 px-4 py-3 last:border-0 dark:border-white/5 ${
                        !n.read ? 'bg-[#ffb100]/5' : ''
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        {!n.read && <span className="h-1.5 w-1.5 rounded-full bg-[#ffb100]" />}
                        <span className="text-sm font-medium text-gray-900 dark:text-white">{n.title}</span>
                      </div>
                      <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{n.detail}</p>
                      <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">{n.time}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* History */}
        <div className="relative">
          <button
            type="button"
            onClick={() => toggleMenu('history')}
            className="rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
            aria-label="History"
          >
            <Clock className="h-5 w-5" />
          </button>

          {openMenu === 'history' && (
            <div className="absolute right-0 top-full z-20 mt-2 w-72 rounded-xl border border-gray-200 bg-white shadow-lg dark:border-white/10 dark:bg-[#171B20]">
              <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-white/10">
                <span className="text-sm font-medium text-gray-900 dark:text-white">Recently Visited</span>
                {history.length > 0 && (
                  <button
                    onClick={clearHistory}
                    className="flex items-center gap-1 text-xs font-medium text-gray-400 hover:text-red-500"
                  >
                    <Trash2 className="h-3 w-3" />
                    Clear
                  </button>
                )}
              </div>

              <div className="max-h-72 overflow-y-auto py-1">
                {history.length === 0 ? (
                  <p className="px-4 py-6 text-center text-sm text-gray-400">No history yet</p>
                ) : (
                  history.map((entry) => {
                    const meta = pageTitles[entry.path]
                    return (
                      <button
                        key={`${entry.path}-${entry.visitedAt}`}
                        onClick={() => {
                          navigate(entry.path)
                          setOpenMenu(null)
                        }}
                        className="flex w-full items-center justify-between px-4 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-white/10"
                      >
                        <span>{meta ? `${meta.section} / ${meta.page}` : entry.path}</span>
                        <span className="ml-3 shrink-0 text-xs text-gray-400 dark:text-gray-500">
                          {formatRelativeTime(entry.visitedAt)}
                        </span>
                      </button>
                    )
                  })
                )}
              </div>
            </div>
          )}
        </div>

        {/* Account */}
        <div className="relative">
          <button
            type="button"
            onClick={() => toggleMenu('account')}
            className="rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
            aria-label="Account settings"
          >
            <UserCog className="h-5 w-5" />
          </button>

          {openMenu === 'account' && (
            <div className="absolute right-0 top-full z-20 mt-2 w-48 rounded-xl border border-gray-200 bg-white p-1 shadow-lg dark:border-white/10 dark:bg-[#171B20]">
              <button
                onClick={() => {
                  navigate('/settings')
                  setOpenMenu(null)
                }}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-white/10"
              >
                <Settings className="h-4 w-4" />
                Settings
              </button>

              <div className="my-1 border-t border-gray-100 dark:border-white/10" />

              <button
                onClick={() => {
                  setOpenMenu(null)
                  setShowLogoutModal(true)
                }}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10"
              >
                <LogOut className="h-4 w-4" />
                Log out
              </button>
            </div>
          )}
        </div>
      </div>

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
                className="rounded-2xl bg-red-500 px-5 py-2 text-sm font-medium text-white hover:bg-red-600"
              >
                Sign Out
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  )
}