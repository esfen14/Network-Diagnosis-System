import { useState, useMemo } from 'react'
import { ArrowUpDown, Filter, Search, Edit } from 'lucide-react'
import type { User } from '../../data/users'

type UserTableProps = { users: User[]; title: string; onEdit: (user: User) => void }

function StatusBadge({ status }: { status: User['status'] }) {
  const styles: Record<User['status'], string> = {
    active:    'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    inactive:  'bg-gray-100    text-gray-600    dark:bg-gray-800        dark:text-gray-400',
    locked:    'bg-yellow-100  text-yellow-700  dark:bg-yellow-900/40   dark:text-yellow-300',
    suspended: 'bg-red-100     text-red-700     dark:bg-red-900/40      dark:text-red-300',
  }
  const dots: Record<User['status'], string> = {
    active: 'bg-emerald-500', inactive: 'bg-gray-400', locked: 'bg-yellow-500', suspended: 'bg-red-500',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dots[status]}`} />
      {status}
    </span>
  )
}

export function UserTable({ users, title, onEdit }: UserTableProps) {
  const [query, setQuery] = useState('')
  const [sortAsc, setSortAsc] = useState(true)
  const [showFilter, setShowFilter] = useState(false)
  const [statusFilter, setStatusFilter] = useState<'All' | User['status']>('All')

  const statuses = useMemo(() => ['All', ...Array.from(new Set(users.map((u) => u.status)))] as const, [users])

  const filtered = useMemo(() => {
    let result = users
    if (statusFilter !== 'All') result = result.filter((u) => u.status === statusFilter)
    if (query.trim()) {
      const q = query.toLowerCase()
      result = result.filter((u) => u.fullName.toLowerCase().includes(q) || u.userId.toLowerCase().includes(q) || u.username.toLowerCase().includes(q))
    }
    return [...result].sort((a, b) => sortAsc ? a.fullName.localeCompare(b.fullName) : b.fullName.localeCompare(a.fullName))
  }, [users, query, statusFilter, sortAsc])

  return (
    <div className="overflow-hidden rounded-2xl bg-[var(--card)] border border-[var(--border)] shadow-sm">

      {/* Sticky header */}
      <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] bg-[var(--card)] p-4">
        <h2 className="text-lg font-semibold text-[var(--text)]">{title}</h2>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2">
            <Search className="h-4 w-4 text-[var(--text-muted)]" />
            <input type="search" placeholder="Search" value={query} onChange={(e) => setQuery(e.target.value)}
              className="w-32 bg-transparent text-sm text-[var(--text)] placeholder:text-[var(--text-muted)] outline-none" />
          </div>

          <div className="relative">
            <button type="button" onClick={() => setShowFilter((v) => !v)}
              className={`rounded-lg p-2 ${showFilter || statusFilter !== 'All' ? 'bg-[var(--hover)] text-[var(--text)]' : 'text-[var(--text-muted)] hover:bg-[var(--hover)]'}`}>
              <Filter className="h-4 w-4" />
            </button>
            {showFilter && (
              <div className="absolute right-0 top-full z-10 mt-2 w-40 rounded-xl border border-[var(--border)] bg-[var(--card)] p-2 shadow-lg">
                <span className="block px-2 py-1 text-xs font-medium text-[var(--text-muted)]">Status</span>
                {statuses.map((s) => (
                  <button key={s} onClick={() => { setStatusFilter(s); setShowFilter(false) }}
                    className={`block w-full rounded-lg px-2 py-1.5 text-left text-sm capitalize hover:bg-[var(--hover)] ${statusFilter === s ? 'text-[#ffb100] font-medium' : 'text-[var(--text)]'}`}>
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button type="button" onClick={() => setSortAsc((v) => !v)} title={sortAsc ? 'Sorted A → Z' : 'Sorted Z → A'}
            className="rounded-lg p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]">
            <ArrowUpDown className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">

        <table className="w-full min-w-[900px] text-left text-sm">
          <thead>
            <tr className="border-b border-[var(--border)] text-xs text-[var(--text-muted)]">
              <th className="px-4 py-3 font-normal">Full Name</th>
              <th className="px-4 py-3 font-normal">User ID</th>
              <th className="px-4 py-3 font-normal">Username</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Joined Date</th>
              <th className="px-4 py-3 font-normal">Last Active</th>
              <th className="px-4 py-3 font-normal">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-[var(--text-muted)]">No users match your search or filter</td></tr>
            ) : (
              filtered.map((user) => (
                <tr key={user.id} className="border-b border-[var(--border)] transition hover:bg-[var(--hover)]">
                  <td className="px-4 py-3 text-[var(--text)]">{user.fullName}</td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">{user.userId}</td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">{user.username}</td>
                  <td className="px-4 py-3"><StatusBadge status={user.status} /></td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">{user.joinedDate}</td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">{user.lastActive}</td>
                  <td className="px-4 py-3">
                    <button type="button" onClick={() => onEdit(user)} className="text-[var(--text-muted)] hover:text-[var(--text)]" title="Edit">
                      <Edit className="h-4 w-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t border-[var(--border)] px-4 py-3 text-sm text-[var(--text-muted)]">
        <span>Showing {filtered.length} of {users.length} users</span>
        <div className="flex gap-2">
          <button type="button" className="rounded-lg px-3 py-1 hover:bg-[var(--hover)]" disabled>Previous</button>
          <button type="button" className="rounded-lg bg-white border border-gray-200 px-3 py-1 text-gray-900 shadow-sm hover:bg-gray-50 dark:bg-white/10 dark:text-white dark:border-transparent dark:hover:bg-white/20">1</button>
          <button type="button" className="rounded-lg px-3 py-1 hover:bg-[var(--hover)]">Next</button>
        </div>
      </div>
    </div>
  )
}
