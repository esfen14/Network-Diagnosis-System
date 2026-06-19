import { useMemo, useState } from 'react'
import { UserTable } from '../components/manage-accounts/UserTable'
import { PageHeader } from '../components/shared/PageHeader'
import { users } from '../data/users'

type StatusFilter =
  | 'all'
  | 'active'
  | 'inactive'
  | 'locked'
  | 'suspended'

export function ManageAccountsPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  const filteredUsers = useMemo(() => {
    if (statusFilter === 'all') return users
    return users.filter((u) => u.status === statusFilter)
  }, [statusFilter])

  return (
    <main className="ml-[220px] flex-1">
      <div className="space-y-6">

        <PageHeader
          title="User Management"
          description="Manage all users in one place. Control access, assign roles, and monitor activity across your platform."
        />

        {/* FILTERS */}
        <div className="flex flex-wrap items-center justify-between gap-4">

          <div className="flex gap-2">
            {(['all', 'active', 'inactive', 'locked', 'suspended'] as StatusFilter[]).map((status) => (
              <button
                key={status}
                onClick={() => setStatusFilter(status)}
                className={`px-4 py-2 rounded-lg text-sm transition ${
                  statusFilter === status
                    ? 'bg-white text-black'
                    : 'bg-white/10 text-gray-300 hover:bg-white/20'
                }`}
              >
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </button>
            ))}
          </div>

          <div className="flex gap-2">
            <button className="px-4 py-2 rounded-lg bg-white/10 text-gray-300 hover:bg-white/20">
              Export
            </button>

            <button className="px-4 py-2 rounded-lg bg-[#ffb100] text-black font-medium">
              + Add User
            </button>
          </div>

        </div>

        {/* TABLE */}
        <UserTable users={filteredUsers} title="All System Users" />

      </div>
    </main>
  )
}