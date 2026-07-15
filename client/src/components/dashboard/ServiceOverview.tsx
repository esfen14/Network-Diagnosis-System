type StatusTone = 'green' | 'yellow' | 'red' | 'blue' | 'gray'

type ServiceItem = {
  label: string
  status: string
  tone: StatusTone
  isHeader?: boolean
}

const toneStyles: Record<StatusTone, string> = {
  green: 'bg-emerald-600',
  yellow: 'bg-yellow-600',
  red: 'bg-red-600',
  blue: 'bg-blue-600',
  gray: 'bg-gray-600',
}

// Placeholder data — replace with a real fetch to the backend's service-status
// endpoint once it's available (e.g. GET /api/service-overview).
const services: ServiceItem[] = [
  { label: 'System Status', status: 'Operational', tone: 'green' },
  { label: 'Monitoring Coverage', status: '', tone: 'gray', isHeader: true },
  { label: 'Network Devices', status: '321 Active', tone: 'blue' },
  { label: 'NRPE Agents', status: '295/321 Active', tone: 'blue' },
  { label: 'Network Health', status: '', tone: 'gray', isHeader: true },
  { label: 'HTTP', status: 'Ok', tone: 'green' },
  { label: 'DNS Server', status: 'Slow Response', tone: 'yellow' },
  { label: 'DHCP Server', status: 'Down', tone: 'red' },
  { label: 'Core Services', status: '', tone: 'gray', isHeader: true },
  { label: 'Nagios', status: 'Running', tone: 'green' },
  { label: 'Database', status: 'Healthy', tone: 'green' },
  { label: 'API Health', status: 'Responsive', tone: 'blue' },
  { label: 'Alerts & Notifications', status: '', tone: 'gray', isHeader: true },
  { label: 'Email Notification', status: 'Embedded', tone: 'blue' },
  { label: 'Alert Severity', status: 'Pending', tone: 'yellow' },
  { label: 'IMAP/POP', status: 'Operational', tone: 'green' },
  { label: 'Critical Alerts', status: '47 Alerts', tone: 'red' },
  { label: 'Warning Alerts', status: '90 Warnings', tone: 'yellow' },
  { label: 'Service Monitoring', status: '', tone: 'gray', isHeader: true },
  { label: 'FTP', status: 'Running', tone: 'green' },
]

export function ServiceOverview() {
  return (
    <aside className="hidden w-72 shrink-0 border-l border-white/10 xl:block">
      <div className="sticky top-0 max-h-screen overflow-y-auto p-4">
        <h3 className="mb-4 text-sm font-semibold text-pinpoint-green">
          Service Overview
        </h3>
        <div className="space-y-1">
          {services.map((item) =>
            item.isHeader ? (
              <p
                key={item.label}
                className="pb-1 pt-3 text-xs font-medium uppercase text-gray-500 first:pt-0"
              >
                {item.label}
              </p>
            ) : (
              <div
                key={item.label}
                className="flex items-center justify-between rounded-xl px-2 py-2 hover:bg-white/5"
              >
                <span className="text-sm text-white/80">{item.label}</span>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-medium text-white ${toneStyles[item.tone]}`}
                >
                  {item.status}
                </span>
              </div>
            ),
          )}
        </div>
      </div>
    </aside>
  )
}