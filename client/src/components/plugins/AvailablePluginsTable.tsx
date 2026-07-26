import { ArrowUpDown, Filter, Plus, Search } from 'lucide-react'
import type { Plugin } from '../../data/plugins'

type Props = {
  data: Plugin[]
  selected: number[]
  onSelect: (id: number) => void
}

export function AvailablePluginsTable({ data, selected, onSelect }: Props) {
  return (
    <div className="overflow-hidden rounded-2xl bg-[#171B20] shadow-sm">

      {/* HEADER */}
      <div className="flex items-center justify-between border-b border-white/10 p-4">
        <h2 className="text-lg font-semibold text-white">Available Plugins</h2>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-[#0D1117] px-3 py-2">
            <Search className="h-4 w-4 text-gray-500" />
            <input
              type="search"
              placeholder="Search"
              className="w-32 bg-transparent text-sm text-white outline-none"
            />
          </div>

          <button className="p-2 text-gray-400 hover:bg-white/10 hover:text-white rounded-lg">
            <Plus className="h-4 w-4" />
          </button>

          <button className="p-2 text-gray-400 hover:bg-white/10 hover:text-white rounded-lg">
            <Filter className="h-4 w-4" />
          </button>

          <button className="p-2 text-gray-400 hover:bg-white/10 hover:text-white rounded-lg">
            <ArrowUpDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* TABLE */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="border-b border-white/10 text-xs text-gray-400">
            <tr>
              <th className="px-4 py-3 text-left"></th>
              <th className="px-4 py-3 text-left">Plugin</th>
              <th className="px-4 py-3 text-left">Category</th>
              <th className="px-4 py-3 text-left">Type</th>
              <th className="px-4 py-3 text-left">Description</th>
              <th className="px-4 py-3 text-left">Status</th>
            </tr>
          </thead>

          <tbody>
            {data.map((p) => (
              <tr key={p.id} className="border-b border-white/5 hover:bg-white/5">
                <td className="px-4 py-3 text-left">
                  <input
                    type="checkbox"
                    checked={selected.includes(p.id)}
                    onChange={() => onSelect(p.id)}
                  />
                </td>
                <td className="px-4 py-3 text-white text-left">{p.name}</td>
                <td className="px-4 py-3 text-gray-300 text-left">{p.category}</td>
                <td className="px-4 py-3 text-gray-300 text-left">{p.type}</td>
                <td className="px-4 py-3 text-gray-300 text-left">{p.description}</td>
                <td className="px-4 py-3 text-yellow-400 text-left">● Available</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* FOOTER */}
      <div className="flex justify-between items-center border-t border-white/10 px-4 py-3 text-sm text-gray-400">
        <span>Showing {data.length} plugins</span>
        <div className="flex gap-2">
          <button className="px-3 py-1 rounded-lg hover:bg-white/10">Previous</button>
          <button className="px-3 py-1 rounded-lg bg-white/10 text-white">1</button>
          <button className="px-3 py-1 rounded-lg hover:bg-white/10">Next</button>
        </div>
      </div>

    </div>
  )
}