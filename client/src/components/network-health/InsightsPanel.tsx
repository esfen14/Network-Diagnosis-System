import type { Insight } from '../../types/networkHealth'
import { formatTimeAgo } from '../../utils/formatDateTime'

const SEVERITY_COLOR: Record<Insight['severity'], string> = {
  critical: 'bg-red-500',
  warning: 'bg-[#F4A90B]',
  info: 'bg-blue-500',
  ok: 'bg-emerald-500',
}

type InsightsPanelProps = {
  // GET /network-health/insights — null while loading.
  insights: Insight[] | null
  insightsError: string | null
  // Plugin types with at least one monitored service
  // (GET /network-health/plugins → groups[].display_name). null while loading.
  supportedChecks: string[] | null
  now: Date
}

export function InsightsPanel({ insights, insightsError, supportedChecks, now }: InsightsPanelProps) {
  return (
    <aside className="hidden w-72 shrink-0 border-l border-[var(--border)] xl:block">
      <div className="sticky top-0 p-4">
        <h3 className="mb-4 text-sm font-semibold text-[var(--text)]">Network Health Insights</h3>
        {insightsError ? (
          <p className="text-sm text-[var(--text-muted)]">{insightsError}</p>
        ) : insights == null ? (
          <p className="text-sm text-[var(--text-muted)]">Loading…</p>
        ) : (
          <div className="space-y-4">
            {insights.map((item) => (
              <div key={item.message} className="flex gap-3">
                <div className={`mt-1 h-8 w-8 shrink-0 rounded-full ${SEVERITY_COLOR[item.severity]}`} aria-label={item.severity} />
                <div>
                  <p className="text-sm leading-snug text-[var(--text)]">{item.message}</p>
                  {item.at && <p className="mt-1 text-xs text-[var(--text-muted)]">{formatTimeAgo(item.at, now)}</p>}
                </div>
              </div>
            ))}
          </div>
        )}
        <h3 className="mb-3 mt-8 text-sm font-semibold text-[var(--text)]">Current Supported Checks</h3>
        {supportedChecks == null ? (
          <p className="text-sm text-[var(--text-muted)]">Loading…</p>
        ) : supportedChecks.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">No checks are being monitored yet.</p>
        ) : (
          <ul className="space-y-2">
            {supportedChecks.map((check) => (
              <li key={check} className="text-sm text-[var(--text-muted)]">{check}</li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
