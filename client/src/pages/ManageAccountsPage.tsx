import { useMemo, useState } from 'react'
import { X } from 'lucide-react'
import { UserTable } from '../components/manage-accounts/UserTable'
import { PageHeader } from '../components/shared/PageHeader'
import { users as initialUsers } from '../data/users'
import type { User } from '../data/users'

type StatusFilter =
  | 'all'
  | 'active'
  | 'inactive'
  | 'locked'
  | 'suspended'

function generateUserId() {
  // abang - just a placeholder-looking hash for now, backend will issue the real one
  return Array.from({ length: 24 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
}

export function ManageAccountsPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [allUsers, setAllUsers] = useState<User[]>(initialUsers)

  const [showAddModal, setShowAddModal] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)

  const [newAccount, setNewAccount] = useState({
    firstName: '',
    lastName: '',
    username: '',
    userId: generateUserId(),
    password: '',
    confirmPassword: '',
  })

  const filteredUsers = useMemo(() => {
    if (statusFilter === 'all') return allUsers
    return allUsers.filter((u) => u.status === statusFilter)
  }, [allUsers, statusFilter])

  const resetAddForm = () => {
    setNewAccount({
      firstName: '',
      lastName: '',
      username: '',
      userId: generateUserId(),
      password: '',
      confirmPassword: '',
    })
  }

  const closeAddModal = () => {
    setShowAddModal(false)
    resetAddForm()
  }

  const addFormValid =
    newAccount.firstName.trim() &&
    newAccount.lastName.trim() &&
    newAccount.username.trim() &&
    newAccount.password &&
    newAccount.password === newAccount.confirmPassword

  const handleAddUser = () => {
    if (!addFormValid) return

    // abang - swap this for the real call once the endpoint's ready
    // POST /api/users { firstName, lastName, username, password }
    const today = new Date().toISOString().split('T')[0]

    const user: User = {
      id: newAccount.userId,
      fullName: `${newAccount.firstName.trim()} ${newAccount.lastName.trim()}`,
      userId: newAccount.userId,
      username: newAccount.username.trim(),
      status: 'active',
      joinedDate: today,
      lastActive: 'Never',
    }

    setAllUsers((prev) => [...prev, user])
    closeAddModal()
  }

  const handleExport = () => {
    // abang - if we ever need the export to hit the backend instead (e.g. for a formatted report),
    // swap this for GET /api/users/export?status=${statusFilter} and download the returned blob
    const headers = ['Full Name', 'User ID', 'Username', 'Status', 'Joined Date', 'Last Active']

    const rows = filteredUsers.map((u) => [
      u.fullName,
      u.userId,
      u.username,
      u.status,
      u.joinedDate,
      u.lastActive,
    ])

    const csvContent = [headers, ...rows]
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n')

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `users-${statusFilter}-${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const handleSaveEdit = (updated: User) => {
    // abang - swap this for the real call once the endpoint's ready
    // PATCH /api/users/:id { ...updated }
    setAllUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
    setEditingUser(null)
  }

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
              onClick={handleExport}
              disabled={filteredUsers.length === 0}
              className="px-4 py-2 rounded-lg bg-white/10 text-gray-300 hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Export
            </button>

            <button
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2 rounded-lg bg-[#ffb100] text-black font-medium"
            >
              + Add User
            </button>
          </div>

        </div>


        <UserTable
          users={filteredUsers}
          title="All System Users"
          onEdit={(user) => setEditingUser(user)}
        />

      </div>

      {/* ADD ACCOUNT MODAL */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="relative w-full max-w-xl rounded-3xl bg-[#0D1117] p-8 shadow-xl">

            <button
              onClick={closeAddModal}
              className="absolute right-5 top-5 text-gray-500 hover:text-gray-300"
            >
              <X className="h-5 w-5" />
            </button>

            <h2 className="text-center text-xl font-semibold text-white">
              Profile Info
            </h2>

            <div className="mt-6 grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  FIRST NAME
                </label>
                <input
                  value={newAccount.firstName}
                  onChange={(e) => setNewAccount({ ...newAccount, firstName: e.target.value })}
                  placeholder="e.g. JUAN"
                  className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  LAST NAME
                </label>
                <input
                  value={newAccount.lastName}
                  onChange={(e) => setNewAccount({ ...newAccount, lastName: e.target.value })}
                  placeholder="e.g. CRUZ"
                  className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  USERNAME
                </label>
                <input
                  value={newAccount.username}
                  onChange={(e) => setNewAccount({ ...newAccount, username: e.target.value })}
                  placeholder="Create a valid username."
                  className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  USER ID
                </label>
                <input
                  value={newAccount.userId}
                  disabled
                  className="w-full rounded-full bg-white/10 px-4 py-2.5 text-sm text-gray-400 outline-none"
                />
              </div>
            </div>

            <div className="my-6 border-t border-white/10" />

            <h2 className="text-center text-xl font-semibold text-white">
              Create Password
            </h2>

            <div className="mt-6 grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  NEW PASSWORD
                </label>
                <input
                  type="password"
                  value={newAccount.password}
                  onChange={(e) => setNewAccount({ ...newAccount, password: e.target.value })}
                  className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  CONFIRM PASSWORD
                </label>
                <input
                  type="password"
                  value={newAccount.confirmPassword}
                  onChange={(e) => setNewAccount({ ...newAccount, confirmPassword: e.target.value })}
                  className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none"
                />
              </div>
            </div>

            {newAccount.password &&
              newAccount.confirmPassword &&
              newAccount.password !== newAccount.confirmPassword && (
                <p className="mt-2 text-center text-xs text-red-400">
                  Passwords do not match.
                </p>
              )}

            <button
              onClick={handleAddUser}
              disabled={!addFormValid}
              className="mx-auto mt-6 block rounded-full bg-[#ffb100] px-10 py-2.5 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
            >
              SAVE CHANGES
            </button>

            <p className="mt-4 text-center text-xs text-gray-500">
              You will be asked to log in again with your new password after you save your changes.
            </p>

          </div>
        </div>
      )}

      {/* EDIT ACCOUNT MODAL */}
      {editingUser && (
        <EditAccountModal
          user={editingUser}
          onCancel={() => setEditingUser(null)}
          onSave={handleSaveEdit}
        />
      )}

    </main>
  )
}

function EditAccountModal({
  user,
  onCancel,
  onSave,
}: {
  user: User
  onCancel: () => void
  onSave: (updated: User) => void
}) {
  const [nameParts, firstName, ...rest] = [
    user.fullName.split(' '),
    user.fullName.split(' ')[0] ?? '',
    ...user.fullName.split(' ').slice(1),
  ]
  const lastName = rest[rest.length - 1] ?? ''
  const middleName = rest.slice(0, -1).join(' ')

  const [form, setForm] = useState({
    firstName,
    lastName,
    middleName,
    username: user.username,
    status: user.status,
  })
  const [showResetFields, setShowResetFields] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const handleSave = () => {
    const updated: User = {
      ...user,
      fullName: [form.firstName, form.middleName, form.lastName].filter(Boolean).join(' '),
      username: form.username,
      status: form.status,
    }
    // abang - if a password reset was triggered, send newPassword along in the PATCH call too
    onSave(updated)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="relative w-full max-w-2xl rounded-3xl bg-[#0D1117] p-8 shadow-xl">

        <button
          onClick={onCancel}
          className="absolute right-5 top-5 text-gray-500 hover:text-gray-300"
        >
          <X className="h-5 w-5" />
        </button>

        <h2 className="text-xl font-semibold text-white">Edit Account</h2>
        <p className="mt-1 text-sm text-gray-400">
          Update personal information of users and reset password securely.
        </p>

        <div className="mt-6 flex items-center gap-2 text-sm">
          <span className="text-gray-400">Last Active</span>
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-sm text-gray-300">
          <span className="h-2 w-2 rounded-full bg-red-500" />
          {user.lastActive}
        </div>

        <div className="mt-6 grid grid-cols-3 gap-4">
          <div>
            <label className="mb-1.5 block text-sm text-gray-300">Last Name</label>
            <input
              value={form.lastName}
              onChange={(e) => setForm({ ...form, lastName: e.target.value })}
              className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm text-gray-300">First Name</label>
            <input
              value={form.firstName}
              onChange={(e) => setForm({ ...form, firstName: e.target.value })}
              className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm text-gray-300">Middle Name</label>
            <input
              value={form.middleName}
              onChange={(e) => setForm({ ...form, middleName: e.target.value })}
              className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1.5 block text-sm text-gray-300">Status</label>
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as User['status'] })}
              className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
            >
              <option value="active" className="bg-[#0D1117]">Active</option>
              <option value="inactive" className="bg-[#0D1117]">Inactive</option>
              <option value="locked" className="bg-[#0D1117]">Locked</option>
              <option value="suspended" className="bg-[#0D1117]">Suspended</option>
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-sm text-gray-300">Username</label>
            <input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1.5 block text-sm text-gray-300">User ID</label>
            <input
              value={user.userId}
              disabled
              className="w-full rounded-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-gray-500 outline-none"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm text-gray-300">Password</label>
            <div className="flex items-center gap-2 rounded-full border border-white/20 py-1 pl-4 pr-1.5">
              <span className="flex-1 text-sm text-gray-500">••••••••••••••••</span>
              <button
                onClick={() => setShowResetFields((v) => !v)}
                className="rounded-full bg-[#ffb100] px-4 py-1.5 text-xs font-semibold text-black"
              >
                Reset
              </button>
            </div>
          </div>
        </div>

        {showResetFields && (
          <div className="mt-4 grid grid-cols-2 gap-4 rounded-xl border border-white/10 p-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                NEW PASSWORD
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                CONFIRM PASSWORD
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none"
              />
            </div>
            {newPassword && confirmPassword && newPassword !== confirmPassword && (
              <p className="col-span-2 text-xs text-red-400">Passwords do not match.</p>
            )}
          </div>
        )}

        <div className="mt-6 flex justify-center gap-3">
          <button
            onClick={onCancel}
            className="rounded-full border border-[#ffb100] px-8 py-2.5 text-sm font-medium text-[#ffb100] hover:bg-[#ffb100]/10"
          >
            Cancel
          </button>

          <button
            onClick={handleSave}
            disabled={
              showResetFields &&
              (!newPassword || newPassword !== confirmPassword)
            }
            className="rounded-full bg-[#ffb100] px-8 py-2.5 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
          >
            Save Changes
          </button>
        </div>

        <p className="mt-4 text-center text-xs text-gray-500">
          The user will be signed out after changes are applied.
        </p>

      </div>
    </div>
  )
}