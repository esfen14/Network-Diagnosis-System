type StatusTone = 'green' | 'yellow' | 'red' | 'blue' | 'gray'
type ServiceItem = { label: string; status: string; tone: StatusTone; isHeader?: boolean }

const toneStyles: Record<StatusTone, string> = {
  green: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  yellow:'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300',
  red:   'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  blue:  'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  gray:  'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400',
}

const services: ServiceItem[] = [
  { label: 'System Status',          status: 'Operational',   tone: 'green' },
  { label: 'Monitoring Coverage',    status: '',              tone: 'gray', isHeader: true },
  { label: 'Network Devices',        status: '321 Active',    tone: 'blue' },
  { label: 'NRPE Agents',            status: '295/321 Active',tone: 'blue' },
  { label: 'Network Health',         status: '',              tone: 'gray', isHeader: true },
  { label: 'HTTP',                   status: 'Ok',            tone: 'green' },
  { label: 'DNS Server',             status: 'Slow Response', tone: 'yellow' },
  { label: 'DHCP Server',            status: 'Down',          tone: 'red' },
  { label: 'Core Services',          status: '',              tone: 'gray', isHeader: true },
  { label: 'Nagios',                 status: 'Running',       tone: 'green' },
  { label: 'Database',               status: 'Healthy',       tone: 'green' },
  { label: 'API Health',             status: 'Responsive',    tone: 'blue' },
  { label: 'Alerts & Notifications', status: '',              tone: 'gray', isHeader: true },
  { label: 'Email Notification',     status: 'Embedded',      tone: 'blue' },
  { label: 'Alert Severity',         status: 'Pending',       tone: 'yellow' },
  { label: 'IMAP/POP',               status: 'Operational',   tone: 'green' },
  { label: 'Critical Alerts',        status: '47 Alerts',     tone: 'red' },
  { label: 'Warning Alerts',         status: '90 Warnings',   tone: 'yellow' },
  { label: 'Service Monitoring',     status: '',              tone: 'gray', isHeader: true },
  { label: 'FTP',                    status: 'Running',       tone: 'green' },
]

export function ServiceOverview() {
  return (
    <aside className="hidden w-72 shrink-0 border-l border-[var(--border)] xl:block">
      <div className="sticky top-0 max-h-screen overflow-y-auto p-4">
        <h3 className="mb-4 text-sm font-semibold text-emerald-600">Service Overview</h3>
        <div className="space-y-1">
          {services.map((item) =>
            item.isHeader ? (
              <p key={item.label} className="pb-1 pt-3 text-xs font-medium uppercase text-[var(--text-muted)] first:pt-0">
                {item.label}
              </p>
            ) : (
              <div key={item.label} className="flex items-center justify-between rounded-xl px-2 py-2 hover:bg-[var(--hover)]">
                <span className="text-sm text-[var(--text)]">{item.label}</span>
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${toneStyles[item.tone]}`}>{item.status}</span>
              </div>
            )
          )}
        </div>
      </div>
    </aside>
  )
}
