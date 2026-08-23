import { useMemo, useState } from 'react'
import { Activity, CheckCircle2, XCircle } from 'lucide-react'
import { DeviceTable } from '../components/device-inventory/DeviceTable.tsx'
import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { devices, routers } from '../data/devices'
import { useSystemSettings } from '../contexts/SystemSettingsContext'

type ViewMode = 'all' | 'router'

export function DeviceInventoryPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('all')
  const [activeRouter, setActiveRouter] = useState<string>('R1')

  const { settings } = useSystemSettings()

  const isLight = settings.theme === 'light'

  const filteredDevices = useMemo(() => {
    if (viewMode === 'all') return devices
    return devices.filter((d) => d.router === activeRouter)
  }, [viewMode, activeRouter])

  const hostTotals = useMemo(() => {
    const online = filteredDevices.filter((d) => d.status === 'Online').length
    const offline = filteredDevices.filter((d) => d.status === 'Offline').length
    return {
      total: filteredDevices.length,
      online,
      offline,
    }
  }, [filteredDevices])

  const titleHighlight =
    viewMode === 'all'
      ? 'All Devices'
      : `Router ${activeRouter}`

  const tableTitle =
    viewMode === 'all'
      ? 'All Devices'
      : `Router ${activeRouter}`

  return (
    <main
      className={`ml-[220px] flex-1 ${
        isLight
          ? 'bg-[#f5f6f8] text-gray-900'
          : 'bg-pinpoint-dark text-white'
      }`}
    >
      <div className="space-y-6">

        <PageHeader
          title="Host Inventory"
          highlight={titleHighlight}
          description={
            viewMode === 'all'
              ? 'Overview of all connected devices in your network infrastructure.'
              : 'Overview of connected devices based on each router in your network infrastructure.'
          }
        />

        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
          <SummaryStatCard
            title="Total Hosts"
            value={String(hostTotals.total)}
            subtitle={viewMode === 'all' ? 'Across all routers' : `On Router ${activeRouter}`}
            icon={Activity}
            gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
          />

          <SummaryStatCard
            title="Online"
            value={String(hostTotals.online)}
            subtitle="Currently reachable"
            icon={CheckCircle2}
            gradient="linear-gradient(135deg,#22C55E,#16A34A)"
          />

          <SummaryStatCard
            title="Offline"
            value={String(hostTotals.offline)}
            subtitle="Currently unreachable"
            icon={XCircle}
            gradient="linear-gradient(135deg,#EF4444,#DC2626)"
          />
        </div>

        <div
          className={`flex gap-6 border-b ${
            isLight
              ? 'border-gray-300'
              : 'border-white/10'
          }`}
        >
          <button
            type="button"
            onClick={() => setViewMode('all')}
            className={`pb-3 text-sm transition ${
              viewMode === 'all'
                ? isLight
                  ? 'border-b-2 border-gray-900 font-medium text-gray-900'
                  : 'border-b-2 border-white font-medium text-white'
                : isLight
                  ? 'text-gray-500 hover:text-gray-900'
                  : 'text-white/60 hover:text-white'
            }`}
          >
            All Devices
          </button>

          <button
            type="button"
            onClick={() => setViewMode('router')}
            className={`pb-3 text-sm transition ${
              viewMode === 'router'
                ? isLight
                  ? 'border-b-2 border-gray-900 font-medium text-gray-900'
                  : 'border-b-2 border-white font-medium text-white'
                : isLight
                  ? 'text-gray-500 hover:text-gray-900'
                  : 'text-white/60 hover:text-white'
            }`}
          >
            Router
          </button>
        </div>

        {viewMode === 'router' && (
          <div className="flex flex-wrap gap-2">
            {routers.map((router) => (
              <button
                key={router}
                type="button"
                onClick={() => setActiveRouter(router)}
                className={`rounded-lg px-4 py-2 text-sm transition ${
                  activeRouter === router
                    ? isLight
                      ? 'bg-gray-900 text-white'
                      : 'bg-white text-black'
                    : isLight
                      ? 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                      : 'bg-white/10 text-gray-300 hover:bg-white/20'
                }`}
              >
                {router}
              </button>
            ))}
          </div>
        )}

        <DeviceTable
          devices={filteredDevices}
          title={tableTitle}
        />
      </div>
    </main>
  )
}