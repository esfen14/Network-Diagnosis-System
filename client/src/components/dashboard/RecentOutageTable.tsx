import { useState } from 'react'
import { MoreHorizontal } from 'lucide-react'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'
import { formatDateTime } from '../../utils/formatDateTime'
import type { AlertRow } from '../../types/dashboard'

type RecentOutageTableProps = {
  alerts: AlertRow[]
  isLoading: boolean
  onAcknowledge: (alert: AlertRow) => void
}

const stateStyles: Record<string, string> = {
  DOWN: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  UNREACHABLE: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  CRITICAL: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  WARNING: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  UNKNOWN: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

export function RecentOutageTable({ alerts, isLoading, onAcknowledge }: RecentOutageTableProps) {
  const { settings } = useSystemSettings()

  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--text)]">Active Alerts</h2>
        <button type="button" className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]" aria-label="More options">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs text-[var(--text-muted)] border-b border-[var(--border)]">
              <th className="pb-3 pr-4 font-medium">Affected Device/Service</th>
              <th className="pb-3 pr-4 font-medium">Since</th>
              <th className="pb-3 pr-4 font-medium">Output</th>
              <th className="pb-3 pr-4 font-medium">Status</th>
              <th className="pb-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5} className="py-8 text-center text-[var(--text-muted)]">Loading…</td></tr>
            ) : alerts.length === 0 ? (
              <tr><td colSpan={5} className="py-8 text-center text-[var(--text-muted)]">No active alerts</td></tr>
            ) : (
              alerts.map((alert) => (
                <tr key={`${alert.hostname}-${alert.serviceName ?? ''}`} className="border-t border-[var(--border)]">
                  <td className="py-3 pr-4 text-[var(--text)]">
                    {alert.hostname}{alert.serviceName ? ` / ${alert.serviceName}` : ''}
                  </td>
                  <td className="py-3 pr-4 text-[var(--text-muted)]">
                    {formatDateTime(new Date(alert.timestamp * 1000), settings.dateTimeFormat, settings.timeZone)}
                  </td>
                  <td className="py-3 pr-4 text-[var(--text-muted)] max-w-xs truncate">{alert.pluginOutput}</td>
                  <td className="py-3 pr-4">
                    <span className={`rounded-full px-3 py-1 text-xs font-medium ${stateStyles[alert.state] ?? stateStyles.UNKNOWN}`}>
                      {alert.state}{alert.inDowntime ? ' · Downtime' : ''}
                    </span>
                  </td>
                  <td className="py-3">
                    {alert.ack ? (
                      <span className="text-xs text-[var(--text-muted)]" title={alert.ack.comment}>
                        Acked by {alert.ack.acknowledgedBy}
                      </span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onAcknowledge(alert)}
                        className="rounded-lg bg-[#ffb100] px-3 py-1 text-xs font-semibold text-black hover:brightness-105"
                      >
                        Acknowledge
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
