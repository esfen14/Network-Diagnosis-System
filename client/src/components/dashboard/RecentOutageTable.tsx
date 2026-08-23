import { MoreHorizontal } from 'lucide-react'

type OutageStatus = 'In Progress' | 'Resolved' | 'Warning' | 'Completed'
type OutageRow = { device: string; dateTime: string; cause: string; status: OutageStatus }

const statusStyles: Record<OutageStatus, string> = {
  'In Progress': 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  Resolved:      'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  Warning:       'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  Completed:     'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
}

const outages: OutageRow[] = [
  { device: 'Access Switch - SW02',  dateTime: 'Oct 21, 2025 - 14:32', cause: 'High CPU & Memory Utilization',       status: 'In Progress' },
  { device: 'Access Switch - SW02',  dateTime: 'Oct 19, 2025 - 15:02', cause: 'Interface G1/0/2 Link Down',           status: 'Resolved'    },
  { device: 'CICT Server - SRV01',   dateTime: 'Oct 17, 2025 - 02:00', cause: 'OS Version 3 Major Releases Behind',   status: 'Warning'     },
  { device: 'Core Network Link',     dateTime: 'Oct 15, 2025 - 09:18', cause: 'ISP Packet Loss Spike (0.3% - 4.5%)', status: 'Resolved'    },
  { device: 'Edge Switch - SW03',    dateTime: 'Oct 14, 2025 - 23:33', cause: 'Unexpected Restart / Power Event',     status: 'Completed'   },
]

export function RecentOutageTable() {
  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--text)]">Recent Outage</h2>
        <button type="button" className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]" aria-label="More options">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs text-[var(--text-muted)] border-b border-[var(--border)]">
              <th className="pb-3 pr-4 font-medium">Affected Device/Link</th>
              <th className="pb-3 pr-4 font-medium">Date &amp; Time</th>
              <th className="pb-3 pr-4 font-medium">Cause</th>
              <th className="pb-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {outages.map((row) => (
              <tr key={row.device + row.dateTime} className="border-t border-[var(--border)]">
                <td className="py-3 pr-4 text-[var(--text)]">{row.device}</td>
                <td className="py-3 pr-4 text-[var(--text-muted)]">{row.dateTime}</td>
                <td className="py-3 pr-4 text-[var(--text-muted)]">{row.cause}</td>
                <td className="py-3">
                  <span className={`rounded-full px-3 py-1 text-xs font-medium ${statusStyles[row.status]}`}>{row.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
