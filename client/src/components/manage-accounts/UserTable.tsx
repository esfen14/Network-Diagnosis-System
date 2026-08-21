import {
  ArrowUpDown,
  Filter,
  Plus,
  Search,
  Edit,
  Download,
} from 'lucide-react'
import type { User } from '../../data/users'

type UserTableProps = {
  users: User[]
  title: string
}

function StatusBadge({ status }: { status: User['status'] }) {
  const styles = {
    active: 'bg-emerald-500/20 text-emerald-400',
    inactive: 'bg-gray-500/20 text-gray-500 dark:text-gray-400',
    locked: 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400',
    suspended: 'bg-red-500/20 text-red-500 dark:text-red-400',
  }

  const dotStyles = {
    active: 'bg-emerald-400',
    inactive: 'bg-gray-400',
    locked: 'bg-yellow-400',
    suspended: 'bg-red-400',
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${styles[status]}`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${dotStyles[status]}`}
      />
      {status}
    </span>
  )
}

export function UserTable({
  users,
  title,
}: UserTableProps) {
  return (
    <div className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {title}
        </h2>

        <div className="flex flex-wrap items-center gap-2">

          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
            <Search className="h-4 w-4 text-gray-500" />

            <input
              type="search"
              placeholder="Search"
              className="w-32 bg-transparent text-sm text-gray-800 placeholder:text-gray-500 outline-none dark:text-white dark:placeholder:text-gray-500"
            />
          </div>

          <button
            type="button"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <Plus className="h-4 w-4" />
          </button>

          <button
            type="button"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <Filter className="h-4 w-4" />
          </button>

          <button
            type="button"
            className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <ArrowUpDown className="h-4 w-4" />
          </button>

        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">

          <thead>
            <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-500">
              <th className="px-4 py-3 font-normal">
                Full Name
              </th>

              <th className="px-4 py-3 font-normal">
                User ID
              </th>

              <th className="px-4 py-3 font-normal">
                Username
              </th>

              <th className="px-4 py-3 font-normal">
                Status
              </th>

              <th className="px-4 py-3 font-normal">
                Joined Date
              </th>

              <th className="px-4 py-3 font-normal">
                Last Commit
              </th>

              <th className="px-4 py-3 font-normal">
                Actions
              </th>
            </tr>
          </thead>

          <tbody>
            {users.map((user) => (
              <tr
                key={user.id}
                className="border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5"
              >
                <td className="px-4 py-3 text-gray-900 dark:text-white">
                  {user.fullName}
                </td>

                <td className="px-4 py-3 text-gray-900 dark:text-white">
                  {user.userId}
                </td>

                <td className="px-4 py-3 text-gray-900 dark:text-white">
                  {user.username}
                </td>

                <td className="px-4 py-3">
                  <StatusBadge status={user.status} />
                </td>

                <td className="px-4 py-3 text-gray-900 dark:text-white">
                  {user.joinedDate}
                </td>

                <td className="px-4 py-3 text-gray-900 dark:text-white">
                  {user.lastActive}
                </td>

                <td className="px-4 py-3">
                  <div className="flex gap-3 text-gray-500 dark:text-gray-400">

                    <button
                      type="button"
                      className="hover:text-gray-900 dark:hover:text-white"
                      title="Edit"
                    >
                      <Edit className="h-4 w-4" />
                    </button>

                    <button
                      type="button"
                      className="hover:text-gray-900 dark:hover:text-white"
                      title="Download"
                    >
                      <Download className="h-4 w-4" />
                    </button>

                  </div>
                </td>
              </tr>
            ))}
          </tbody>

        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>
          Showing {users.length} users
        </span>

        <div className="flex gap-2">

          <button
            type="button"
            className="rounded-lg px-3 py-1 hover:bg-gray-100 dark:hover:bg-white/10"
            disabled
          >
            Previous
          </button>

          <button
            type="button"
            className="rounded-lg bg-gray-900 px-3 py-1 text-white dark:bg-white/10"
          >
            1
          </button>

          <button
            type="button"
            className="rounded-lg px-3 py-1 hover:bg-gray-100 dark:hover:bg-white/10"
          >
            Next
          </button>

        </div>
      </div>

    </div>
  )
}