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
  const [statusFilter, setStatusFilter] =
    useState<StatusFilter>('all')

  const filteredUsers = useMemo(() => {
    if (statusFilter === 'all') {
      return users
    }

    return users.filter((u) => u.status === statusFilter)
  }, [statusFilter])

  return (
    <main className="ml-[220px] flex-1">
      <div className="space-y-6">

        {/* HEADER */}
        <PageHeader
          title="User Management"
          description="Manage all users in one place. Control access, assign roles, and monitor activity across your platform."
        />

        {/* TABS + ACTIONS */}
        <div className="flex flex-wrap items-center justify-between gap-4">

          {/* STATUS TABS */}
          <div className="flex gap-6 border-b border-white/10">
            {(
              [
                'all',
                'active',
                'inactive',
                'locked',
                'suspended',
              ] as StatusFilter[]
            ).map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`pb-3 text-sm transition ${
                  statusFilter === status
                    ? 'border-b-2 border-white font-medium text-white'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {status === 'all'
                  ? 'All'
                  : status.charAt(0).toUpperCase() + status.slice(1)}
              </button>
            ))}
          </div>

          {/* ACTION BUTTONS */}
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded-lg bg-white/10 px-4 py-2 text-gray-300 transition hover:bg-white/20"
            >
              Export
            </button>

            <button
              type="button"
              className="rounded-lg bg-[#ffb100] px-4 py-2 font-medium text-black transition hover:bg-[#e6a000]"
            >
              + Add User
            </button>
          </div>

        </div>

        {/* USER TABLE */}
        <UserTable
          users={filteredUsers}
          title="All System Users"
        />

      </div>
    </main>
  )
}