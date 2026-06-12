import { ArrowUpDown, Filter, Plus, Search } from 'lucide-react'
import type { Device } from '../../data/devices'

type DeviceTableProps = {
  devices: Device[]
  title: string
}

function StatusBadge({ status }: { status: Device['status'] }) {
  const isOnline = status === 'Online'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
        isOnline
          ? 'bg-emerald-500/20 text-emerald-400'
          : 'bg-red-500/20 text-red-400'
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${isOnline ? 'bg-emerald-400' : 'bg-red-400'}`}
      />
      {status}
    </span>
  )
}

export function DeviceTable({ devices, title }: DeviceTableProps) {
  return (
    <div className="overflow-hidden rounded-2xl bg-[#171B20] shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-4">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#0D1117] px-3 py-2">
            <Search className="h-4 w-4 text-gray-500" />
            <input
              type="search"
              placeholder="Search"
              className="w-32 bg-transparent text-sm text-white placeholder:text-gray-500 outline-none"
            />
          </div>
          <button
            type="button"
            className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white"
            aria-label="Add device"
          >
            <Plus className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white"
            aria-label="Filter"
          >
            <Filter className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white"
            aria-label="Sort"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs text-gray-500">
              <th className="px-4 py-3 font-normal">
                <input type="checkbox" className="rounded border-gray-600" aria-label="Select all" />
              </th>
              <th className="px-4 py-3 font-normal">Device ID</th>
              <th className="px-4 py-3 font-normal">Host Name</th>
              <th className="px-4 py-3 font-normal">Device Type</th>
              <th className="px-4 py-3 font-normal">Device IP</th>
              <th className="px-4 py-3 font-normal">OS Version</th>
              <th className="px-4 py-3 font-normal">Router</th>
              <th className="px-4 py-3 font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device, i) => (
              <tr
                key={device.id}
                className={`border-b border-white/5 transition hover:bg-white/5 ${
                  i === 4 ? 'bg-white/5' : ''
                }`}
              >
                <td className="px-4 py-3">
                  <input type="checkbox" className="rounded border-gray-600" aria-label={`Select ${device.id}`} />
                </td>
                <td className="px-4 py-3 text-white">{device.id}</td>
                <td className="px-4 py-3 text-white">{device.hostName}</td>
                <td className="px-4 py-3 text-white">{device.deviceType}</td>
                <td className="px-4 py-3 text-white">{device.deviceIp}</td>
                <td className="px-4 py-3 text-white">{device.osVersion}</td>
                <td className="px-4 py-3 text-white">{device.router}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={device.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-white/10 px-4 py-3 text-sm text-gray-400">
        <span>Showing {devices.length} devices</span>
        <div className="flex gap-2">
          <button type="button" className="rounded-lg px-3 py-1 hover:bg-white/10" disabled>
            Previous
          </button>
          <button type="button" className="rounded-lg bg-white/10 px-3 py-1 text-white">
            1
          </button>
          <button type="button" className="rounded-lg px-3 py-1 hover:bg-white/10">
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
