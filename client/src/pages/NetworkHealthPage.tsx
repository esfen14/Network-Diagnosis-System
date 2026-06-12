import { MonitorOff, MonitorSmartphone, Timer, WifiOff } from 'lucide-react'
import { ActiveConnectionsCard } from '../components/network-health/ActiveConnectionsCard'
import { CpuUtilizationChart } from '../components/network-health/CpuUtilizationChart'
import { DeviceCountCard } from '../components/network-health/DeviceCountCard'
import { HostAvailabilityCard } from '../components/network-health/HostAvailabilityCard'
import { InsightsPanel } from '../components/network-health/InsightsPanel'
import { NetworkInfoCard } from '../components/network-health/NetworkInfoCard'
import { ResourceUsageCard } from '../components/network-health/ResourceUsageCard'
import { SparklineMetricCard } from '../components/network-health/SparklineMetricCard'
import { SystemActivityCard } from '../components/network-health/SystemActivityCard'
import { TrendStatCard } from '../components/network-health/TrendStatCard'
import { PageHeader } from '../components/shared/PageHeader'

const latencySparkline = [8, 12, 10, 14, 11, 13, 12.5]
const bandwidthSparkline = [820, 840, 835, 860, 845, 850, 848]

export function NetworkHealthPage() {
  return (
    <main className="ml-[220px] flex-1">
    <div className="flex gap-0">
      <div className="min-w-0 flex-1 space-y-6">
        <PageHeader
          title="Network Health"
          description="Overview of system performance."
        />

        <div className="grid grid-cols-12 gap-4">
      
          <div className="col-span-5">
            <NetworkInfoCard />
          </div>

          <div className="col-span-7 grid grid-cols-2 gap-4">
            <SparklineMetricCard
              title="Latency"
              value="12.5"
              unit="ms"
              change="+9.2%"
              changeType="positive"
              sparklineData={latencySparkline}
              sparklineColor="#10B981"
            />

            <SparklineMetricCard
              title="Bandwidth"
              value="850"
              unit="mbps"
              change="-1.02%"
              changeType="negative"
              sparklineData={bandwidthSparkline}
              sparklineColor="#E70D0D"
            />

            <TrendStatCard
              title="Packets Loss"
              value="0.3%"
              change="-0.5%"
              changeType="positive"
              icon={WifiOff}
            />

            <TrendStatCard
              title="Avg. Response Time"
              value="32 ms"
              change="-0.3%"
              changeType="negative"
              icon={Timer}
            />
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <DeviceCountCard
            title="Online Devices"
            count={321}
            icon={MonitorSmartphone}
            iconBg="bg-emerald-500"
          />

          <DeviceCountCard
            title="Offline Devices"
            count={66}
            icon={MonitorOff}
            iconBg="bg-red-700"
          />

          <div className="sm:col-span-2">
            <HostAvailabilityCard />
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-1">
            <ActiveConnectionsCard />
          </div>

          <div className="lg:col-span-2">
            <ResourceUsageCard />
          </div>
        </div>

 
        <div className="grid gap-4 lg:grid-cols-2">
          <SystemActivityCard />
          <CpuUtilizationChart />
        </div>
      </div>

      <div className="w-[280px] shrink-0 border-l border-[#1D2633] pl-6">
        <InsightsPanel />
      </div>
    </div>
    </main>
  )
}