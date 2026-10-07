import { useEffect, useRef, useState } from 'react'
import { Bell, CheckCircle2, Clock, HelpCircle, LogOut, PanelLeft, Radar, Settings, Star, Trash2, UserCog, XCircle } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router-dom'
import { apiGet, apiPost } from '../../lib/api'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'
import { useCurrentUser } from '../../contexts/CurrentUserContext'
import { fromRawNotification, formatRelativeTime as formatNotificationTime, type NotificationItem, type NotificationsResponse } from '../../types/notification'
import { useDiscoveryStatus, type DiscoveryStatus } from '../../hooks/useDiscoveryStatus'
import { useNcpaDeploymentStatus } from '../../hooks/useNcpaDeploymentStatus'
import { DeploymentStatusItem } from '../ncpa-deployment/DeploymentStatusItem'

const pageTitles: Record<string, { section: string; page: string }> = {
  '/dashboard': { section: 'Dashboards', page: 'Overview' },
  '/network-health': { section: 'Network Health', page: 'Overview' },
  '/device-inventory': { section: 'Host Inventory', page: 'Overview' },
  '/topology': { section: 'System Status', page: 'All Hosts' },
  '/plugins': { section: 'Plugins', page: 'System Plugins' },
  '/ncpa-deployment': { section: 'Plugins', page: 'NCPA Deployment' },
  '/history': { section: 'History', page: 'Alerts & Notifications' },
  '/reports': { section: 'Reports', page: 'System Reports' },
  '/system-logs': { section: 'System Logs', page: 'All' },
  '/accounts': { section: 'Management', page: 'Manage Accounts' },
  '/settings': { section: 'Management', page: 'Settings' },
}

const FAVORITES_KEY = 'nds:favorites'
const HISTORY_KEY = 'nds:history'
const MAX_HISTORY = 15

type HistoryEntry = {
  path: string
  visitedAt: number
}

const UNREAD_POLL_INTERVAL_MS = 30_000

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

// Top entry of the notification panel: the latest network discovery scan.
// Shows live progress and a Cancel button while it runs, then its outcome.
function ScanStatusItem({
  scan,
  isCancelling,
  cancelError,
  onCancel,
}: {
  scan: DiscoveryStatus
  isCancelling: boolean
  cancelError: string | null
  onCancel: () => void
}) {
  const finishedAt = scan.completedAt ?? scan.startAt
  const finishedTime = formatNotificationTime(Math.floor(finishedAt.getTime() / 1000))

  if (scan.status === 'Running') {
    return (
      <div className="border-b border-gray-100 bg-[#ffb100]/5 px-4 py-3 dark:border-white/10">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-white">
            <Radar className="h-4 w-4 animate-pulse text-[#ffb100]" />
            {isCancelling ? 'Cancelling network scan…' : 'Network scan in progress'}
          </span>
          <button
            type="button"
            onClick={onCancel}
            disabled={isCancelling}
            className="rounded-lg border border-gray-200 px-2 py-0.5 text-xs font-medium text-gray-600 hover:border-red-300 hover:text-red-500 disabled:cursor-default disabled:opacity-50 disabled:hover:border-gray-200 disabled:hover:text-gray-600 dark:border-white/10 dark:text-gray-300"
          >
            {isCancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        </div>
        <div
          className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-white/10"
          role="progressbar"
          aria-label="Network scan progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={scan.progress}
        >
          <div className="h-full rounded-full bg-[#ffb100] transition-all" style={{ width: `${scan.progress}%` }} />
        </div>
        <div className="mt-1 flex justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span className="truncate">{scan.message}</span>
          <span className="shrink-0">{scan.progress}%</span>
        </div>
        {cancelError && (
          <p role="alert" className="mt-1 text-xs text-red-600 dark:text-red-400">{cancelError}</p>
        )}
      </div>
    )
  }

  const outcome = {
    Success: { icon: <CheckCircle2 className="h-4 w-4 text-green-500" />, title: 'Network scan complete' },
    Failed: { icon: <XCircle className="h-4 w-4 text-red-500" />, title: 'Network scan failed' },
    Interrupted: { icon: <XCircle className="h-4 w-4 text-gray-400" />, title: 'Network scan cancelled' },
  }[scan.status]

  return (
    <div className="border-b border-gray-100 px-4 py-3 dark:border-white/10">
      <span className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-white">
        {outcome.icon}
        {outcome.title}
      </span>
      <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
        {scan.status === 'Failed' && scan.error ? scan.error : scan.message}
      </p>
      <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">{finishedTime}</p>
    </div>
  )
}

const STATE_BADGE: Record<string, string> = {
  CRITICAL: 'bg-red-500/15 text-red-600 dark:text-red-400',
  FAILED: 'bg-red-500/15 text-red-600 dark:text-red-400',
  WARNING: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  CANCELLED: 'bg-gray-500/15 text-gray-600 dark:text-gray-400',
  OK: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  SUCCESS: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
}

function StateBadge({ state }: { state: string }) {
  if (!state) return null
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${STATE_BADGE[state] ?? 'bg-gray-500/15 text-gray-600 dark:text-gray-400'}`}>
      {state}
    </span>
  )
}

function SourceBadge({ source }: { source: NotificationItem['source'] }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
        source === 'pinpoint' ? 'bg-[#ffb100]/20 text-[#b37a00] dark:text-[#ffb100]' : 'bg-sky-500/15 text-sky-700 dark:text-sky-300'
      }`}
    >
      {source === 'pinpoint' ? 'Pinpoint' : 'Nagios'}
    </span>
  )
}

function notificationTitle(n: NotificationItem) {
  if (n.source === 'pinpoint') return n.serviceName ?? 'Pinpoint notification'
  const title = `${n.type} ${n.hostname || 'Unknown host'}${n.serviceName ? ` / ${n.serviceName}` : ''}`.trim()
  return n.repeatCount > 1 ? `${title} (×${n.repeatCount})` : title
}

function NotificationDetailModal({
  notification,
  onClose,
  onViewHistory,
}: {
  notification: NotificationItem
  onClose: () => void
  onViewHistory?: () => void
}) {
  const when = new Date(notification.timestamp * 1000).toLocaleString()
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Notification details"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-3xl border border-[var(--border)] bg-[var(--card)] p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-wrap items-center gap-2">
          <SourceBadge source={notification.source} />
          <StateBadge state={notification.state} />
          <span className="text-xs text-[var(--text-muted)]">{when}</span>
        </div>
        <h2 className="mt-3 text-lg font-semibold text-[var(--text)]">{notificationTitle(notification)}</h2>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-[var(--text-muted)]">{notification.source === 'pinpoint' ? 'Origin' : 'Host'}</dt>
          <dd className="text-[var(--text)]">{notification.hostname || '—'}</dd>
          {notification.source === 'nagios' && (
            <>
              <dt className="text-[var(--text-muted)]">Service</dt>
              <dd className="text-[var(--text)]">{notification.serviceName ?? 'Host check'}</dd>
            </>
          )}
        </dl>
        <p className="mt-4 text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">Description</p>
        <pre className="mt-1 max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded-xl bg-[var(--hover)] p-3 text-sm text-[var(--text)]">
          {notification.fullMessage || 'No description available.'}
        </pre>
        <div className="mt-6 flex justify-end gap-3">
          {onViewHistory && (
            <button
              type="button"
              onClick={onViewHistory}
              className="rounded-2xl border border-[var(--border)] px-5 py-2 text-sm font-medium text-[var(--text)] hover:bg-[var(--hover)]"
            >
              View history
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className="rounded-2xl bg-[#ffb100] px-5 py-2 text-sm font-medium text-black hover:brightness-95"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

export function Header() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { hasPermission } = useCurrentUser()
  const notificationsEnabled =
    useSystemSettings().savedSettings.notifications && hasPermission('system.notifications')
  const canDiscover = hasPermission('system.discover')
  const discovery = useDiscoveryStatus(canDiscover)
  const isScanning = discovery.scan?.status === 'Running'
  const canDeployNcpa = hasPermission('system.deploy.ncpa')
  const deployment = useNcpaDeploymentStatus(canDeployNcpa)
  const isDeploying = deployment.run?.status === 'Running'
  const showBell = notificationsEnabled || canDiscover || canDeployNcpa
  const showActivityDot = isScanning || discovery.hasUnseenResult || isDeploying || deployment.hasUnseenResult

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

  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [isLoadingNotifications, setIsLoadingNotifications] = useState(false)

  const [openMenu, setOpenMenu] = useState<'notifications' | 'history' | 'account' | null>(null)
  const menuRef = useOutsideClick(() => setOpenMenu(null))

  const [showLogoutModal, setShowLogoutModal] = useState(false)
  const [selectedNotification, setSelectedNotification] = useState<NotificationItem | null>(null)

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

  // Poll the lightweight unread-count endpoint to drive the bell badge.
  useEffect(() => {
    if (!notificationsEnabled) return

    async function pollUnread() {
      try {
        const data = await apiGet<{ unread_count: number }>('/api/system/notifications/unread-count')
        setUnreadCount(data.unread_count)
      } catch {
      }
    }
    pollUnread()
    const id = window.setInterval(pollUnread, UNREAD_POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [notificationsEnabled])

  useEffect(() => {
    if (openMenu !== 'notifications' || !notificationsEnabled) return

    let cancelled = false
    setIsLoadingNotifications(true)

    apiGet<NotificationsResponse>('/api/system/notifications?limit=20')
      .then((data) => {
        if (cancelled) return
        setNotifications(data.notifications.map(fromRawNotification))
        setUnreadCount(data.unread_count)
      })
      .catch(() => {
      })
      .finally(() => {
        if (!cancelled) setIsLoadingNotifications(false)
      })

    return () => {
      cancelled = true
    }
  }, [openMenu, notificationsEnabled])

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

  const markAllRead = async () => {
    const newestTs = notifications.reduce((max, n) => Math.max(max, n.timestamp), 0)
    setNotifications((prev) => prev.map((n) => ({ ...n, isRead: true })))
    setUnreadCount(0)
    try {
      await apiPost('/api/system/notifications/mark-read', newestTs > 0 ? { up_to: newestTs } : {})
    } catch {
      // Non-fatal — worst case the next poll/open re-syncs the real count.
    }
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
  if (menu === 'notifications') {
    discovery.markSeen()
    deployment.markSeen()
  }
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
        {showBell && (
          <div className="relative">
            <button
              type="button"
              onClick={() => toggleMenu('notifications')}
              className="relative rounded-2xl p-2 text-gray-500 transition hover:bg-black/5 hover:text-gray-900 dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white"
              aria-label="Notifications"
            >
              <Bell className="h-5 w-5" />
              {notificationsEnabled && unreadCount > 0 ? (
                <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-medium text-white">
                  {unreadCount}
                </span>
              ) : showActivityDot && (
                <span
                  className={`absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[#ffb100] ${isScanning || isDeploying ? 'animate-pulse' : ''}`}
                  aria-label={
                    isScanning
                      ? 'Network scan in progress'
                      : isDeploying
                        ? 'NCPA deployment in progress'
                        : discovery.hasUnseenResult
                          ? 'Network scan finished'
                          : 'NCPA deployment finished'
                  }
                />
              )}
            </button>

            {openMenu === 'notifications' && (
              <div className="absolute right-0 top-full z-20 mt-2 w-80 rounded-xl border border-gray-200 bg-white shadow-lg dark:border-white/10 dark:bg-[#171B20]">
                <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-white/10">
                  <span className="text-sm font-medium text-gray-900 dark:text-white">Notifications</span>
                  {notificationsEnabled && unreadCount > 0 && (
                    <button
                      onClick={markAllRead}
                      className="text-xs font-medium text-[#ffb100] hover:underline"
                    >
                      Mark all read
                    </button>
                  )}
                </div>

                {canDiscover && discovery.scan && (discovery.scan.status === 'Running' || !notificationsEnabled) && (
                  <ScanStatusItem
                    scan={discovery.scan}
                    isCancelling={discovery.isCancelling}
                    cancelError={discovery.cancelError}
                    onCancel={discovery.cancel}
                  />
                )}

                {canDeployNcpa && deployment.run && (
                  <DeploymentStatusItem
                    run={deployment.run}
                    isCancelling={deployment.isCancelling}
                    cancelError={deployment.cancelError}
                    onCancel={deployment.cancel}
                    onReview={(runId) => {
                      setOpenMenu(null)
                      navigate(`/ncpa-deployment?tab=history&run=${runId}`)
                    }}
                  />
                )}

                <div className="max-h-72 overflow-y-auto">
                  {!notificationsEnabled ? null : isLoadingNotifications ? (
                    <p className="px-4 py-6 text-center text-sm text-gray-400">Loading…</p>
                  ) : notifications.length === 0 ? (
                    <p className="px-4 py-6 text-center text-sm text-gray-400">No notifications</p>
                  ) : (
                    notifications.map((n) => (
                      <button
                        type="button"
                        key={n.id}
                        onClick={() => {
                          setSelectedNotification(n)
                          setOpenMenu(null)
                        }}
                        className={`block w-full cursor-pointer border-b border-gray-50 px-4 py-3 text-left last:border-0 hover:bg-black/5 dark:border-white/5 dark:hover:bg-white/5 ${
                          !n.isRead ? 'bg-[#ffb100]/5' : ''
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          {!n.isRead && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-[#ffb100]" />}
                          <SourceBadge source={n.source} />
                          <StateBadge state={n.state} />
                        </div>
                        <p className="mt-1 text-sm font-medium text-gray-900 dark:text-white">{notificationTitle(n)}</p>
                        <p className="mt-0.5 line-clamp-2 text-xs text-gray-500 dark:text-gray-400">{n.message}</p>
                        <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">{formatNotificationTime(n.timestamp)}</p>
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        )}

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

      {selectedNotification && (
        <NotificationDetailModal
          notification={selectedNotification}
          onClose={() => setSelectedNotification(null)}
          onViewHistory={
            hasPermission('system.history')
              ? () => {
                  setSelectedNotification(null)
                  navigate('/history')
                }
              : undefined
          }
        />
      )}

      {showLogoutModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-3xl border border-[var(--border)] bg-[var(--card)] p-8 text-center shadow-xl">
            <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#F4A90B]">
              <HelpCircle className="h-7 w-7 text-white" />
            </div>

            <h2 className="text-lg font-semibold text-[var(--text)]">
              Sign out of PinPoint?
            </h2>

            <p className="mt-2 text-sm text-[var(--text-muted)]">
              Are you sure you want to sign out? You will need to log in again
              to access the system.
            </p>

            <div className="mt-6 flex justify-center gap-3">
              <button
                onClick={() => setShowLogoutModal(false)}
                className="rounded-2xl border border-[var(--border)] px-5 py-2 text-sm font-medium text-[var(--text)] hover:bg-[var(--hover)]"
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