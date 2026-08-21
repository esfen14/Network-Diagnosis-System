import { ArrowUpDown, Filter, Search } from 'lucide-react'
import type { Plugin } from '../../data/plugins'

type Props = {
  data: Plugin[]
  selected: number[]
  onSelect: (id: number) => void
}

export function InstalledPluginsTable({ data, selected, onSelect }: Props) {
  return (
    <div className="overflow-hidden rounded-2xl bg-white dark:bg-[#171B20] shadow-sm">

      {/* HEADER */}
      <div className="flex items-center justify-between border-b border-gray-200 dark:border-white/10 p-4">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          Installed Plugins
        </h2>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-[#0D1117] px-3 py-2">
            <Search className="h-4 w-4 text-gray-500" />
            <input
              type="search"
              placeholder="Search"
              className="w-32 bg-transparent text-sm text-gray-900 placeholder:text-gray-500 outline-none dark:text-white"
            />
          </div>

          <button className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white">
            <Filter className="h-4 w-4" />
          </button>

          <button className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white">
            <ArrowUpDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* TABLE */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="border-b border-gray-200 dark:border-white/10 text-xs text-gray-500 dark:text-gray-400">
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
              <tr
                key={p.id}
                className="border-b border-gray-100 hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
              >
                <td className="px-4 py-3 text-left">
                  <input
                    type="checkbox"
                    checked={selected.includes(p.id)}
                    onChange={() => onSelect(p.id)}
                  />
                </td>

                <td className="px-4 py-3 text-left text-gray-900 dark:text-white">
                  {p.name}
                </td>

                <td className="px-4 py-3 text-left text-gray-600 dark:text-gray-300">
                  {p.category}
                </td>

                <td className="px-4 py-3 text-left text-gray-600 dark:text-gray-300">
                  {p.type}
                </td>

                <td className="px-4 py-3 text-left text-gray-600 dark:text-gray-300">
                  {p.description}
                </td>

                <td className="px-4 py-3 text-left text-green-600 dark:text-green-400">
                  ● Running
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* FOOTER */}
      <div className="flex items-center justify-between border-t border-gray-200 dark:border-white/10 px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
        <span>Showing {data.length} plugins</span>

        <div className="flex gap-2">
          <button className="rounded-lg px-3 py-1 hover:bg-gray-100 dark:hover:bg-white/10">
            Previous
          </button>

          <button className="rounded-lg bg-gray-100 px-3 py-1 text-gray-900 dark:bg-white/10 dark:text-white">
            1
          </button>

          <button className="rounded-lg px-3 py-1 hover:bg-gray-100 dark:hover:bg-white/10">
            Next
          </button>
        </div>
      </div>

    </div>
  )
}