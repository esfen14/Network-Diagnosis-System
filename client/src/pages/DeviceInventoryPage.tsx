import { useMemo, useState } from 'react'
import { DeviceTable } from '../components/device-inventory/DeviceTable.tsx'
import { PageHeader } from '../components/shared/PageHeader'
import { devices, routers } from '../data/devices'

type ViewMode = 'all' | 'router'

export function DeviceInventoryPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('all')
  const [activeRouter, setActiveRouter] = useState<string>('R1')

  const filteredDevices = useMemo(() => {
    if (viewMode === 'all') return devices
    return devices.filter((d) => d.router === activeRouter)
  }, [viewMode, activeRouter])

  const titleHighlight = viewMode === 'all' ? 'All Devices' : `Router ${activeRouter}`
  const tableTitle = viewMode === 'all' ? 'All Devices' : `Router ${activeRouter}`

  return (
    <main className="ml-[220px] flex-1">
    <div className="space-y-6">
      <PageHeader
        title="Device Inventory"
        highlight={titleHighlight}
        description={
          viewMode === 'all'
            ? 'Overview of all connected devices in your network infrastructure.'
            : 'Overview of connected devices based on each router in your network infrastructure.'
        }
      />

      <div className="flex gap-6 border-b border-white/10">
        <button
          type="button"
          onClick={() => setViewMode('all')}
          className={`pb-3 text-sm transition ${
            viewMode === 'all'
              ? 'border-b-2 border-white font-medium text-white'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          All Devices
        </button>
        <button
          type="button"
          onClick={() => setViewMode('router')}
          className={`pb-3 text-sm transition ${
            viewMode === 'router'
              ? 'border-b-2 border-white font-medium text-white'
              : 'text-gray-500 hover:text-gray-300'
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
                  ? 'bg-white text-black'
                  : 'bg-white/10 text-gray-300 hover:bg-white/20'
              }`}
            >
              {router}
            </button>
          ))}
        </div>
      )}

      <DeviceTable devices={filteredDevices} title={tableTitle} />
    </div>
    </main>
  )
}
