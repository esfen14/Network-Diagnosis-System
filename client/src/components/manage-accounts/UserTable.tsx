import { useState, useMemo, useEffect } from 'react'
import { ArrowUpDown, Filter, Search, Edit } from 'lucide-react'
import type { User } from '../../types/user'

type UserTableProps = { users: User[]; title: string; onEdit: (user: User) => void }

function StatusBadge({ status }: { status: User['status'] }) {
  const styles: Record<User['status'], string> = {
    active:    'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    inactive:  'bg-gray-100    text-gray-600    dark:bg-gray-800        dark:text-gray-400',
    suspended: 'bg-red-100     text-red-700     dark:bg-red-900/40      dark:text-red-300',
  }
  const dots: Record<User['status'], string> = {
    active: 'bg-emerald-500', inactive: 'bg-gray-400', suspended: 'bg-red-500',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status]}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dots[status]}`} />
      {status}
    </span>
  )
}

function formatDate(iso: string) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

const PAGE_SIZE = 10

type SortField = 'name' | 'email' | 'role' | 'status' | 'createdAt'

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: 'name', label: 'Alphabetical' },
  { value: 'email', label: 'Email' },
  { value: 'role', label: 'Role' },
  { value: 'status', label: 'Status' },
  { value: 'createdAt', label: 'Date Added' },
]

function compareBy(field: SortField, a: User, b: User): number {
  switch (field) {
    case 'name':
      return a.fullName.localeCompare(b.fullName)
    case 'email':
      return a.email.localeCompare(b.email)
    case 'role':
      return a.role.localeCompare(b.role)
    case 'status':
      return a.status.localeCompare(b.status)
    case 'createdAt':
      return a.createdAt.localeCompare(b.createdAt)
  }
}

export function UserTable({ users, title, onEdit }: UserTableProps) {
  const [query, setQuery] = useState('')
  const [sortAsc, setSortAsc] = useState(true)
  const [showFilter, setShowFilter] = useState(false)
  const [sortField, setSortField] = useState<SortField>('name')
  const [page, setPage] = useState(1)

  const filtered = useMemo(() => {
    let result = users
    if (query.trim()) {
      const q = query.toLowerCase()
      result = result.filter((u) => u.fullName.toLowerCase().includes(q) || u.email.toLowerCase().includes(q))
    }
    return [...result].sort((a, b) => {
      const cmp = compareBy(sortField, a, b)
      return sortAsc ? cmp : -cmp
    })
  }, [users, query, sortField, sortAsc])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)

  useEffect(() => {
    setPage(1)
  }, [query, sortField, sortAsc, users])

  const paginated = useMemo(
    () => filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
    [filtered, currentPage]
  )

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
              className={`rounded-lg p-2 ${showFilter ? 'bg-[var(--hover)] text-[var(--text)]' : 'text-[var(--text-muted)] hover:bg-[var(--hover)]'}`}
              title="Sort by">
              <Filter className="h-4 w-4" />
            </button>
            {showFilter && (
              <div className="absolute right-0 top-full z-10 mt-2 w-44 rounded-xl border border-[var(--border)] bg-[var(--card)] p-2 shadow-lg">
                <span className="block px-2 py-1 text-xs font-medium text-[var(--text-muted)]">Sort by</span>
                {SORT_OPTIONS.map((opt) => (
                  <button key={opt.value} onClick={() => { setSortField(opt.value); setShowFilter(false) }}
                    className={`block w-full rounded-lg px-2 py-1.5 text-left text-sm hover:bg-[var(--hover)] ${sortField === opt.value ? 'text-[#ffb100] font-medium' : 'text-[var(--text)]'}`}>
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          <button type="button" onClick={() => setSortAsc((v) => !v)} title={sortAsc ? 'Ascending' : 'Descending'}
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
              <th className="px-4 py-3 font-normal">Email</th>
              <th className="px-4 py-3 font-normal">Role</th>
              <th className="px-4 py-3 font-normal">Status</th>
              <th className="px-4 py-3 font-normal">Joined Date</th>
              <th className="px-4 py-3 font-normal">Actions</th>
            </tr>
          </thead>
          <tbody>
            {paginated.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-[var(--text-muted)]">No users match your search or filter</td></tr>
            ) : (
              paginated.map((user) => (
                <tr key={user.id} className="border-b border-[var(--border)] transition hover:bg-[var(--hover)]">
                  <td className="px-4 py-3 text-[var(--text)]">{user.fullName}</td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">{user.email}</td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">{user.role}</td>
                  <td className="px-4 py-3"><StatusBadge status={user.status} /></td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">{formatDate(user.createdAt)}</td>
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
        <span>
          Showing {filtered.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1}
          –{Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length} users
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
            className="rounded-lg px-3 py-1 hover:bg-[var(--hover)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Previous
          </button>
          <span className="rounded-lg bg-white border border-gray-200 px-3 py-1 text-gray-900 shadow-sm dark:bg-white/10 dark:text-white dark:border-transparent">
            {currentPage} / {pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
            disabled={currentPage >= pageCount}
            className="rounded-lg px-3 py-1 hover:bg-[var(--hover)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}
