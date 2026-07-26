import { ArrowUpDown, Download, Filter, Search } from 'lucide-react'

function StatusBadge({ status }: { status: 'Up' | 'Down' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
        status === 'Up'
          ? 'bg-emerald-500/20 text-emerald-400'
          : 'bg-red-500/20 text-red-400'
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          status === 'Up' ? 'bg-emerald-400' : 'bg-red-400'
        }`}
      />
      {status}
    </span>
  )
}

export function AllDevicesReportTable() {
  type Device = {
  id: number
  deviceId: string
  temperature: number
  cpu: number
  memory: number
  status: 'Up' | 'Down'
  uptime: string
  timestamp: string
}

const devices: Device[] = Array.from({ length: 10 }).map((_, index) => ({
    id: index + 1,
    deviceId: `DEV-${String(index + 1).padStart(3, '0')}`,
    temperature: Math.floor(Math.random() * 20) + 35,
    cpu: Math.floor(Math.random() * 70) + 10,
    memory: Math.floor(Math.random() * 60) + 25,
    status: index % 5 === 0 ? 'Down' : 'Up',
    uptime: (99 + Math.random()).toFixed(2),
    timestamp: '2026-07-26 09:15:42',
  }))

  return (
    <div className="overflow-hidden rounded-2xl bg-[#171B20] shadow-sm">
      <div className="flex items-center justify-between border-b border-white/10 p-4">
        <h2 className="text-lg font-semibold text-white">
          All Devices Report
        </h2>

        <div className="flex gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#0D1117] px-3 py-2">
            <Search className="h-4 w-4 text-gray-500" />
            <input
              placeholder="Search"
              className="bg-transparent text-sm text-white outline-none"
            />
          </div>

          <button className="rounded-lg p-2 hover:bg-white/10">
            <Filter className="h-4 w-4 text-gray-400" />
          </button>

          <button className="rounded-lg p-2 hover:bg-white/10">
            <ArrowUpDown className="h-4 w-4 text-gray-400" />
          </button>

          <button className="rounded-lg p-2 hover:bg-white/10">
            <Download className="h-4 w-4 text-gray-400" />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1100px] text-left text-sm">
          <thead className="border-b border-white/10 text-gray-500">
            <tr>
              <th className="px-4 py-3">Device ID</th>
              <th className="px-4 py-3">Temperature (°C)</th>
              <th className="px-4 py-3">CPU Utilization (%)</th>
              <th className="px-4 py-3">Memory Utilization (%)</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Uptime (%)</th>
              <th className="px-4 py-3">Timestamp</th>
            </tr>
          </thead>

          <tbody>
            {devices.map((device) => (
              <tr
                key={device.id}
                className="border-b border-white/5 hover:bg-white/5"
              >
                <td className="px-4 py-3 text-white">{device.deviceId}</td>
                <td className="px-4 py-3 text-white">{device.temperature}°C</td>
                <td className="px-4 py-3 text-white">{device.cpu}%</td>
                <td className="px-4 py-3 text-white">{device.memory}%</td>
                <td className="px-4 py-3">
                  <StatusBadge status={device.status} />
                </td>
                <td className="px-4 py-3 text-white">{device.uptime}%</td>
                <td className="px-4 py-3 text-white">{device.timestamp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-white/10 px-4 py-3 text-sm text-gray-400">
        <span>Showing {devices.length} records</span>

        <div className="flex gap-2">
          <button disabled className="rounded-lg px-3 py-1 hover:bg-white/10">
            Previous
          </button>

          <button className="rounded-lg bg-white/10 px-3 py-1 text-white">
            1
          </button>

          <button className="rounded-lg px-3 py-1 hover:bg-white/10">
            Next
          </button>
        </div>
      </div>
    </div>
  )
}