import { useState, useMemo } from 'react'
import { ArrowUpDown, Filter, Search } from 'lucide-react'
import type { Plugin } from '../../data/plugins'

type Props = {
  data: Plugin[]
  selected: number[]
  onSelect: (id: number) => void
}

export function InstalledPluginsTable({ data, selected, onSelect }: Props) {
  const [query, setQuery] = useState('')
  const [sortAsc, setSortAsc] = useState(true)
  const [showFilter, setShowFilter] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState<string>('All')

  const categories = useMemo(
    () => ['All', ...Array.from(new Set(data.map((p) => p.category)))],
    [data]
  )

  const filtered = useMemo(() => {
    let result = data

    if (categoryFilter !== 'All') {
      result = result.filter((p) => p.category === categoryFilter)
    }

    if (query.trim()) {
      const q = query.toLowerCase()
      result = result.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.category.toLowerCase().includes(q) ||
          p.type.toLowerCase().includes(q) ||
          p.description.toLowerCase().includes(q)
      )
    }

    result = [...result].sort((a, b) =>
      sortAsc ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name)
    )

    return result
  }, [data, query, categoryFilter, sortAsc])

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
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-32 bg-transparent text-sm text-gray-900 placeholder:text-gray-500 outline-none dark:text-white"
            />
          </div>

          {/* Filter */}
          <div className="relative">
            <button
              onClick={() => setShowFilter((v) => !v)}
              className={`rounded-lg p-2 ${
                showFilter || categoryFilter !== 'All'
                  ? 'bg-gray-200 text-gray-900 dark:bg-white/20 dark:text-white'
                  : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white'
              }`}
            >
              <Filter className="h-4 w-4" />
            </button>

            {showFilter && (
              <div className="absolute right-0 top-full z-10 mt-2 w-48 rounded-xl border border-gray-200 bg-white p-2 shadow-lg dark:border-white/10 dark:bg-[#171B20]">
                <span className="block px-2 py-1 text-xs font-medium text-gray-400">
                  Category
                </span>
                {categories.map((c) => (
                  <button
                    key={c}
                    onClick={() => {
                      setCategoryFilter(c)
                      setShowFilter(false)
                    }}
                    className={`block w-full rounded-lg px-2 py-1.5 text-left text-sm ${
                      categoryFilter === c
                        ? 'bg-[#ffb100]/20 text-[#ffb100]'
                        : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/10'
                    }`}
                  >
                    {c}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Sort */}
          <button
            onClick={() => setSortAsc((v) => !v)}
            title={sortAsc ? 'Sorted A → Z' : 'Sorted Z → A'}
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* TABLE */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-225 text-sm">
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
            {filtered.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-4 py-8 text-center text-gray-500 dark:text-gray-400"
                >
                  No plugins match your search or filter
                </td>
              </tr>
            ) : (
              filtered.map((p) => (
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
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* FOOTER */}
      <div className="flex items-center justify-between border-t border-gray-200 dark:border-white/10 px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
        <span>Showing {filtered.length} of {data.length} plugins</span>

        <div className="flex gap-2">
          <button className="rounded-lg px-3 py-1 hover:bg-gray-100 dark:hover:bg-white/10">
            Previous
          </button>

          <button className="rounded-lg bg-white border border-gray-200 px-3 py-1 text-gray-900 shadow-sm hover:bg-gray-50 dark:bg-white/10 dark:text-white dark:border-transparent dark:hover:bg-white/20">
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