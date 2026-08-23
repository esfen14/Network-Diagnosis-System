import { useState } from 'react'
import { CheckCircle2, HelpCircle, MonitorOff, MonitorSmartphone, RefreshCw, Timer, WifiOff, X } from 'lucide-react'
import { ActiveConnectionsCard } from '../components/network-health/ActiveConnectionsCard'
import { CpuLoadChart } from '../components/network-health/CpuLoadChart'
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

type ScanState = 'idle' | 'confirm' | 'scanning' | 'success'

export function NetworkHealthPage() {
  const [scanState, setScanState] = useState<ScanState>('idle')

  const startScan = () => setScanState('confirm')
  const closeModal = () => setScanState('idle')

  const confirmScan = () => {
    setScanState('scanning')
    // Placeholder delay - replace with an actual await fetch(...) call to the
    // backend's rescan endpoint once it exists, then setScanState('success') on response.
    setTimeout(() => {
      setScanState('success')
    }, 2500)
  }

  return (
    <main className="flex-1 overflow-x-auto ml-55">
      <div className="min-w-350 pl-6 pr-8"> 
        <div className="flex items-start gap-8">
          <div className="min-w-0 flex-1">
            <PageHeader
              title="Network Health"
              description="Overview of system performance."
            />
          </div>

          <div className="flex w-72 shrink-0 justify-center pl-4 pt-2">
            <button
              type="button"
              onClick={startScan}
              className="flex items-center gap-2 rounded-3xl bg-[#F4A90B] px-4 py-2 text-sm font-medium text-white shadow-md transition hover:opacity-90"
            >
              <RefreshCw className="h-4 w-4" />
              Last Scan: 1 Hour Ago
            </button>
          </div>
        </div>

        <div className="mt-6 flex items-start gap-8">
          <div className="min-w-0 flex-1 space-y-6">
            <div className="grid grid-cols-12 items-stretch gap-4">
              <div className="col-span-5 flex flex-col gap-4">
                <NetworkInfoCard />
                <div className="flex-1">
                  <ResourceUsageCard />
                </div>
              </div>

              <div className="col-span-7 flex flex-col gap-4">
                <div className="grid grid-cols-2 gap-4">
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
                </div>

                <HostAvailabilityCard />
                <SystemActivityCard />
              </div>
            </div>

            <div className="space-y-4">
              <CpuUtilizationChart />
              <CpuLoadChart />
            </div>
          </div>

          <div className="flex w-72 shrink-0 flex-col gap-4">
            <div className="space-y-4 border-l border-[#1D2633] pl-6">
              <SparklineMetricCard
                title="Latency"
                value="12.5"
                unit="ms"
                change="+9.2%"
                changeType="positive"
                sparklineData={latencySparkline}
                sparklineColor="#10B981"
              />

              <TrendStatCard
                title="Packets Loss"
                value="0.3%"
                change="-0.5%"
                changeType="positive"
                icon={WifiOff}
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
                title="Avg. Response Time"
                value="32 ms"
                change="-0.3%"
                changeType="negative"
                icon={Timer}
              />

              <ActiveConnectionsCard />
            </div>

            <InsightsPanel />
          </div>
        </div>
      </div>

      {scanState !== 'idle' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="relative w-full max-w-sm rounded-3xl bg-white p-8 text-center shadow-xl">
            {scanState !== 'scanning' && (
              <button
                type="button"
                onClick={closeModal}
                aria-label="Close"
                className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            )}

            {scanState === 'confirm' && (
              <>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#F4A90B]">
                  <HelpCircle className="h-7 w-7 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Confirm Network Rescan
                </h3>
                <p className="mt-2 text-sm text-gray-500">
                  Are you sure you want to rescan the network? This action will
                  re-analyze all connected devices and update the current
                  network health status.
                </p>
                <div className="mt-6 flex justify-center gap-3">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-2xl border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={confirmScan}
                    className="rounded-2xl bg-emerald-500 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                  >
                    Confirm
                  </button>
                </div>
              </>
            )}

            {scanState === 'scanning' && (
              <>
                <div className="mx-auto mb-4 h-14 w-14 animate-spin rounded-full border-4 border-blue-200 border-t-blue-500" />
                <h3 className="text-lg font-semibold text-gray-900">
                  Scanning in Progress
                </h3>
                <p className="mt-2 text-sm text-gray-500">
                  Please wait. Do not close the system.
                </p>
              </>
            )}

            {scanState === 'success' && (
              <>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-blue-500">
                  <CheckCircle2 className="h-8 w-8 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Rescan successful!
                </h3>
                <div className="mt-6 flex justify-center">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-2xl bg-emerald-500 px-8 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                  >
                    OK
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </main>
  )
}