// Mirrors GET /api/system/notifications — raw Nagios archivejson notification
// events (not normalized server-side, unlike dashboard.py's own notification
// feed), annotated with a per-user is_read flag. Field names vary between
// archivejson versions, so this mapper is tolerant of multiple aliases —
// mirrors the same normalization dashboard.py's _normalize_notification does.

export type NotificationSource = 'nagios' | 'pinpoint'

export type NotificationItem = {
  id: string
  source: NotificationSource
  timestamp: number
  type: string
  state: string
  hostname: string
  serviceName: string | null
  message: string
  fullMessage: string
  isRead: boolean
}

type RawNotification = Record<string, unknown> & { is_read: boolean }

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function fromRawNotification(raw: RawNotification, index: number): NotificationItem {
  const timestamp = (() => {
    const rawTs = typeof raw.timestamp === 'number' ? raw.timestamp : 0
    return rawTs > 9_999_999_999 ? Math.floor(rawTs / 1000) : rawTs
  })()

  if (raw.source === 'pinpoint') {
    const fullMessage = str(raw.message)
    return {
      id: `pinpoint-${String(raw.id ?? index)}`,
      source: 'pinpoint',
      timestamp,
      type: 'SCAN',
      state: str(raw.state).toUpperCase(),
      hostname: 'Pinpoint',
      serviceName: str(raw.title) || null,
      message: fullMessage.slice(0, 200),
      fullMessage,
      isRead: raw.is_read,
    }
  }

  const hostname = str(raw.hostname) || str(raw.host_name)
  const fullMessage = str(raw.output) || str(raw.plugin_output) || str(raw.notificationreason) || str(raw.state)

  return {
    id: `${hostname}-${timestamp}-${index}`,
    source: 'nagios',
    timestamp,
    type: (str(raw.notificationtype) || str(raw.type)).toUpperCase(),
    state: (str(raw.notificationreason) || str(raw.state)).toUpperCase(),
    hostname,
    serviceName: str(raw.servicedesc) || str(raw.description) || null,
    message: fullMessage.slice(0, 200),
    fullMessage,
    isRead: raw.is_read,
  }
}

export type NotificationsResponse = {
  last_seen_ts: number
  unread_count: number
  notifications: RawNotification[]
}

export function formatRelativeTime(unixSeconds: number): string {
  const diffMs = Date.now() - unixSeconds * 1000
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return new Date(unixSeconds * 1000).toLocaleDateString()
}
