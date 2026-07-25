import { AlertTriangle, Gauge, Server, Wifi } from 'lucide-react'
import { NetworkPerformanceSection } from '../components/dashboard/NetworkPerformanceSection'
import { NetworkStatusOverview } from '../components/dashboard/NetworkStatusOverview'
import { NetworkUptimeSection } from '../components/dashboard/NetworkUptimeSection'
import { RecentOutageTable } from '../components/dashboard/RecentOutageTable'
import { RescanButton } from '../components/dashboard/RescanButton'
import { ResourceUtilizationSection } from '../components/dashboard/ResourceUtilizationSection'
import { ServiceOverview } from '../components/dashboard/ServiceOverview'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'

export function DashboardPage() {
  return (
    <main className="ml-[220px] flex-1">
      <div className="flex gap-0">
        <div className="min-w-0 flex-1 space-y-6 p-6">

          <div className="rounded-3xl bg-[#1a1f26] p-6 shadow-lg">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">CICT Network</h2>
                <p className="text-sm text-gray-400">Last Scan: Today 02:52:08 PM</p>
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <span className="h-2.5 w-2.5 rounded-full bg-pinpoint-green-bright" />
                  <span className="text-sm text-pinpoint-green">Online</span>
                </div>
                <RescanButton />
              </div>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryStatCard
              title="Total Devices"
              value="387"
              subtitle="321 online"
              icon={Server}
              gradient="linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%)"
            />
            <SummaryStatCard
              title="Network Latency"
              value="Good"
              subtitle="12.5ms"
              icon={Wifi}
              gradient="linear-gradient(135deg, #065f46 0%, #10b981 100%)"
            />
            <SummaryStatCard
              title="Active Warnings"
              value="6"
              subtitle="Needs attention"
              icon={AlertTriangle}
              gradient="linear-gradient(135deg, #92400e 0%, #f59e0b 100%)"
            />
            <SummaryStatCard
              title="Critical Issues"
              value="2"
              subtitle="Immediate action"
              icon={Gauge}
              gradient="linear-gradient(135deg, #7f1d1d 0%, #dc2626 100%)"
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <NetworkStatusOverview />
            <NetworkPerformanceSection />
          </div>

          <ResourceUtilizationSection />

          <NetworkUptimeSection />

          <RecentOutageTable />

        </div>

        <ServiceOverview />
      </div>
    </main>
  )
}