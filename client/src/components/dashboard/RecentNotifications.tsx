import { Link } from 'react-router-dom'
import { useCurrentUser } from '../../contexts/CurrentUserContext'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'
import { formatDateTime } from '../../utils/formatDateTime'


export type DashboardNotification = {
  timestamp: number
  type: string
  hostname: string
  service_name: string | null
  state: string
  contact: string
  message: string
}

type RecentNotificationsProps = {
  notifications: DashboardNotification[] | null
  isLoading: boolean
}

export function RecentNotifications({ notifications, isLoading }: RecentNotificationsProps) {
  const { settings } = useSystemSettings()
  const { hasPermission } = useCurrentUser()

  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--text)]">Recent Notifications</h2>
        {hasPermission('system.history') && (
          <Link to="/history" className="text-xs text-[var(--text-muted)] underline hover:text-[var(--text)]">
            View full history
          </Link>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs text-[var(--text-muted)] border-b border-[var(--border)]">
              <th className="pb-3 pr-4 font-medium">Time</th>
              <th className="pb-3 pr-4 font-medium">Device/Service</th>
              <th className="pb-3 pr-4 font-medium">State</th>
              <th className="pb-3 pr-4 font-medium">Contact</th>
              <th className="pb-3 font-medium">Message</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5} className="py-6 text-center text-[var(--text-muted)]">Loading…</td></tr>
            ) : notifications === null ? (
              <tr><td colSpan={5} className="py-6 text-center text-[var(--text-muted)]">Unavailable</td></tr>
            ) : notifications.length === 0 ? (
              <tr><td colSpan={5} className="py-6 text-center text-[var(--text-muted)]">No recent notifications</td></tr>
            ) : (
              notifications.map((n, i) => (
                <tr key={`${n.hostname}-${n.timestamp}-${i}`} className="border-t border-[var(--border)]">
                  <td className="py-3 pr-4 whitespace-nowrap text-[var(--text-muted)]">
                    {formatDateTime(new Date(n.timestamp * 1000), settings.dateTimeFormat, settings.timeZone)}
                  </td>
                  <td className="py-3 pr-4 text-[var(--text)]">
                    {n.hostname}{n.service_name ? ` / ${n.service_name}` : ''}
                  </td>
                  <td className="py-3 pr-4 text-[var(--text)]">{n.state || '—'}</td>
                  <td className="py-3 pr-4 text-[var(--text-muted)]">{n.contact || '—'}</td>
                  <td className="py-3 text-[var(--text-muted)] max-w-xs truncate">{n.message}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
