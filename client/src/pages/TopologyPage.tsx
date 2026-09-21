import { useMemo } from 'react'
import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import {
  ServiceStatusTable,
  type ServiceRow,
} from '../components/system-status/ServiceStatusTable'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  XCircle,
} from 'lucide-react'

// abang - dummy data lang muna to base sa current network status screen,
// palitan pag naka-connect na tayo sa monitoring backend (polling every 90s daw dati)
const services: ServiceRow[] = [
  { id: 1, host: '192.168.130.130.test.local', service: 'rtsp-5000-TCP', status: 'OK', lastCheck: '08-22-2026 09:08:04', duration: '0d 21h 10m 13s' },
  { id: 2, host: '192.168.130.130.test.local', service: 'ssh-22-TCP', status: 'OK', lastCheck: '08-22-2026 09:10:34', duration: '0d 21h 7m 43s' },
  { id: 3, host: '192.168.130.3.test.local', service: 'http-3128-TCP', status: 'OK', lastCheck: '08-22-2026 09:08:22', duration: '0d 21h 9m 55s' },
  { id: 4, host: '192.168.130.3.test.local', service: 'rpcbind-111-TCP', status: 'OK', lastCheck: '08-22-2026 09:07:42', duration: '0d 21h 10m 52s' },
  { id: 5, host: '192.168.130.3.test.local', service: 'ssh-22-TCP', status: 'OK', lastCheck: '08-22-2026 09:08:41', duration: '0d 21h 9m 36s' },
  { id: 6, host: '_gateway', service: 'domain-53-UDP', status: 'Unknown', lastCheck: '08-22-2026 09:09:44', duration: '0d 21h 7m 46s' },
  { id: 7, host: 'localhost', service: 'Current Load', status: 'OK', lastCheck: '08-22-2026 09:09:00', duration: '164d 20h 49m 49s' },
  { id: 8, host: 'localhost', service: 'Current Users', status: 'OK', lastCheck: '08-22-2026 09:10:42', duration: '164d 20h 49m 11s' },
  { id: 9, host: 'localhost', service: 'HTTP', status: 'OK', lastCheck: '08-22-2026 09:09:19', duration: '164d 20h 48m 34s' },
  { id: 10, host: 'localhost', service: 'PING', status: 'OK', lastCheck: '08-22-2026 09:08:13', duration: '164d 20h 52m 56s' },
  { id: 11, host: 'localhost', service: 'Root Partition', status: 'OK', lastCheck: '08-22-2026 09:09:37', duration: '164d 20h 52m 19s' },
  { id: 12, host: 'localhost', service: 'SSH', status: 'OK', lastCheck: '08-22-2026 09:09:39', duration: '164d 20h 51m 41s' },
  { id: 13, host: 'localhost', service: 'Swap Usage', status: 'OK', lastCheck: '08-22-2026 09:09:56', duration: '164d 20h 51m 4s' },
  { id: 14, host: 'localhost', service: 'Total Processes', status: 'OK', lastCheck: '08-22-2026 09:09:21', duration: '164d 20h 50m 26s' },
  { id: 15, host: 'nagios', service: 'http-80-TCP', status: 'OK', lastCheck: '08-22-2026 09:10:15', duration: '0d 21h 10m 37s' },
  { id: 16, host: 'nagios', service: 'ssh-22-TCP', status: 'OK', lastCheck: '08-22-2026 09:07:26', duration: '0d 21h 8m 58s' },
]

export function TopologyPage() {
  const serviceTotals = useMemo(() => {
    const counts = { ok: 0, warning: 0, unknown: 0, critical: 0, pending: 0 }
    services.forEach((s) => {
      if (s.status === 'OK') counts.ok++
      else if (s.status === 'Warning') counts.warning++
      else if (s.status === 'Unknown') counts.unknown++
      else if (s.status === 'Critical') counts.critical++
      else counts.pending++
    })
    return counts
  }, [])

  return (
    <main className="ml-[220px] flex-1">
      <div className="space-y-6">

        <PageHeader
          title="Service Status"
          highlight="Overview"
          description="Live status of hosts and monitored services across your network."
        />

        <div className="grid grid-cols-1 gap-5 md:grid-cols-5">
          <SummaryStatCard
            title="OK"
            value={String(serviceTotals.ok)}
            subtitle="Running normally"
            icon={CheckCircle2}
            gradient="linear-gradient(135deg,#22C55E,#16A34A)"
          />
          <SummaryStatCard
            title="Warning"
            value={String(serviceTotals.warning)}
            subtitle="Needs attention"
            icon={AlertTriangle}
            gradient="linear-gradient(135deg,#EAB308,#CA8A04)"
          />
          <SummaryStatCard
            title="Unknown"
            value={String(serviceTotals.unknown)}
            subtitle="Check inconclusive"
            icon={HelpCircle}
            gradient="linear-gradient(135deg,#FF8A00,#FF5C00)"
          />
          <SummaryStatCard
            title="Critical"
            value={String(serviceTotals.critical)}
            subtitle="Service down"
            icon={XCircle}
            gradient="linear-gradient(135deg,#EF4444,#DC2626)"
          />
          <SummaryStatCard
            title="Pending"
            value={String(serviceTotals.pending)}
            subtitle="Awaiting first check"
            icon={Activity}
            gradient="linear-gradient(135deg,#6B7280,#4B5563)"
          />
        </div>

        <ServiceStatusTable services={services} />

      </div>
    </main>
  )
}