import { ArrowUpDown, Download, Filter, Search } from 'lucide-react'
import type { Report } from '../../data/reports'

type LinkHealthReportTableProps = {
  reports: Report[]
  title?: string
}

export function LinkHealthReportTable({
  reports,
  title = 'Link Health Report',
}: LinkHealthReportTableProps) {
  return (
    <div className="overflow-hidden rounded-2xl bg-[#171B20] shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-4">
        <h2 className="text-lg font-semibold text-white">{title}</h2>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#0D1117] px-3 py-2">
            <Search className="h-4 w-4 text-gray-500" />

            <input
              type="search"
              placeholder="Search"
              className="w-36 bg-transparent text-sm text-white placeholder:text-gray-500 outline-none"
            />
          </div>

          <button className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white">
            <Filter className="h-4 w-4" />
          </button>

          <button className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white">
            <ArrowUpDown className="h-4 w-4" />
          </button>

          <button className="rounded-lg p-2 text-gray-400 hover:bg-white/10 hover:text-white">
            <Download className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1200px] text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs text-gray-500">
              <th className="px-4 py-3 font-normal">Link ID</th>
              <th className="px-4 py-3 font-normal">Local Interface</th>
              <th className="px-4 py-3 font-normal">Remote Interface</th>
              <th className="px-4 py-3 font-normal">Remote Device</th>
              <th className="px-4 py-3 font-normal">Link Speed</th>
              <th className="px-4 py-3 font-normal">Link Type</th>
              <th className="px-4 py-3 font-normal">Discovery Method</th>
              <th className="px-4 py-3 font-normal">Duplex</th>
              <th className="px-4 py-3 font-normal">Timestamp</th>
            </tr>
          </thead>

          <tbody>
            {reports.map((report) => (
              <tr
                key={report.id}
                className="border-b border-white/5 transition hover:bg-white/5"
              >
                <td className="px-4 py-3 text-white">{report.linkId}</td>
                <td className="px-4 py-3 text-white">{report.localInterface}</td>
                <td className="px-4 py-3 text-white">{report.remoteInterface}</td>
                <td className="px-4 py-3 text-white">{report.remoteDevice}</td>
                <td className="px-4 py-3 text-white">{report.linkSpeed}</td>
                <td className="px-4 py-3 text-white">{report.linkType}</td>
                <td className="px-4 py-3 text-white">{report.discoveryMethod}</td>
                <td className="px-4 py-3 text-white">{report.duplex}</td>
                <td className="px-4 py-3 text-white">{report.timestamp}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-white/10 px-4 py-3 text-sm text-gray-400">
        <span>Showing {reports.length} records</span>

        <div className="flex gap-2">
          <button
            disabled
            className="rounded-lg px-3 py-1 hover:bg-white/10"
          >
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