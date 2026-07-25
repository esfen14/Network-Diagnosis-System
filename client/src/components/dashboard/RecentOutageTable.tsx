import { MoreHorizontal } from 'lucide-react'

type OutageStatus = 'In Progress' | 'Resolved' | 'Warning' | 'Completed'

type OutageRow = {
  device: string
  dateTime: string
  cause: string
  status: OutageStatus
}

const statusStyles: Record<OutageStatus, string> = {
  'In Progress': 'bg-purple-600',
  Resolved: 'bg-emerald-600',
  Warning: 'bg-red-600',
  Completed: 'bg-yellow-600',
}

const outages: OutageRow[] = [
  {
    device: 'Access Switch - SW02',
    dateTime: 'Oct 21, 2025 - 14:32',
    cause: 'High CPU & Memory Utilization',
    status: 'In Progress',
  },
  {
    device: 'Access Switch - SW02',
    dateTime: 'Oct 19, 2025 - 15:02',
    cause: 'Interface G1/0/2 Link Down',
    status: 'Resolved',
  },
  {
    device: 'CICT Server - SRV01',
    dateTime: 'Oct 17, 2025 - 02:00',
    cause: 'OS Version 3 Major Releases Behind',
    status: 'Warning',
  },
  {
    device: 'Core Network Link',
    dateTime: 'Oct 15, 2025 - 09:18',
    cause: 'ISP Packet Loss Spike (0.3% - 4.5%)',
    status: 'Resolved',
  },
  {
    device: 'Edge Switch - SW03',
    dateTime: 'Oct 14, 2025 - 23:33',
    cause: 'Unexpected Restart / Power Event',
    status: 'Completed',
  },
]

export function RecentOutageTable() {
  return (
    <div className="rounded-3xl bg-[#1a1f26] p-6 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Recent Outage</h2>
        <button
          type="button"
          className="rounded-2xl bg-white/10 p-2 text-white/70 hover:bg-white/20"
          aria-label="More options"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs uppercase text-gray-500">
              <th className="pb-3 pr-4 font-medium">Affected Device/Link</th>
              <th className="pb-3 pr-4 font-medium">Date &amp; Time</th>
              <th className="pb-3 pr-4 font-medium">Cause</th>
              <th className="pb-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {outages.map((row) => (
              <tr key={row.device + row.dateTime} className="border-t border-white/5">
                <td className="py-3 pr-4 text-white">{row.device}</td>
                <td className="py-3 pr-4 text-gray-400">{row.dateTime}</td>
                <td className="py-3 pr-4 text-gray-400">{row.cause}</td>
                <td className="py-3">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-medium text-white ${statusStyles[row.status]}`}
                  >
                    {row.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}