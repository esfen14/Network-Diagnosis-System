import { useEffect, useMemo, useState } from 'react'
import { X } from 'lucide-react'
import { UserTable } from '../components/manage-accounts/UserTable'
import { PageHeader } from '../components/shared/PageHeader'
import { useSystemSettings } from '../contexts/SystemSettingsContext'
import { apiGet, apiPost, apiPut, errorMessage } from '../lib/api'
import { fromAccountRecord, type RoleOption, type User, type UserStatus } from '../types/user'

// Mirrors server/app/api/helper/validation.py's validate_password() — kept
// in sync with the Strong Password Policy setting so the client-side check
// matches whatever the backend will actually enforce.
const STRONG_MIN_PASSWORD_LENGTH = 12
const RELAXED_MIN_PASSWORD_LENGTH = 8

function isPasswordValid(password: string, strongPolicy: boolean) {
  if (strongPolicy) {
    return (
      password.length >= STRONG_MIN_PASSWORD_LENGTH &&
      /[A-Z]/.test(password) &&
      /[a-z]/.test(password) &&
      /[0-9]/.test(password) &&
      /[^A-Za-z0-9]/.test(password)
    )
  }
  return password.length >= RELAXED_MIN_PASSWORD_LENGTH
}

const SELECT_CLASS =
  'h-10 w-full rounded-xl border border-white/10 bg-white/5 px-3 text-sm text-white outline-none transition duration-200 focus:border-[#ffb100]'

type StatusFilter = 'all' | UserStatus

const STATUS_OPTIONS: UserStatus[] = ['active', 'inactive', 'suspended']

async function fetchAccounts(): Promise<User[]> {
  const data = await apiGet<{ items: Parameters<typeof fromAccountRecord>[0][] }>(
    '/api/user/accounts?per_page=100'
  )
  return data.items.map(fromAccountRecord)
}

async function fetchRoleOptions(): Promise<RoleOption[]> {
  const data = await apiGet<{ items: RoleOption[] }>('/api/user/roles/options')
  return data.items
}

export function ManageAccountsPage() {
  const { settings } = useSystemSettings()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [allUsers, setAllUsers] = useState<User[]>([])
  const [roleOptions, setRoleOptions] = useState<RoleOption[]>([])

  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [showAddModal, setShowAddModal] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setLoadError(null)
      try {
        const [users, roles] = await Promise.all([fetchAccounts(), fetchRoleOptions()])
        if (cancelled) return
        setAllUsers(users)
        setRoleOptions(roles)
      } catch (err) {
        if (cancelled) return
        setLoadError(errorMessage(err, 'Unable to load users.'))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  async function refreshUsers() {
    try {
      setAllUsers(await fetchAccounts())
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to refresh users.'))
    }
  }

  const filteredUsers = useMemo(() => {
    if (statusFilter === 'all') return allUsers
    return allUsers.filter((u) => u.status === statusFilter)
  }, [allUsers, statusFilter])

  const handleExport = () => {
    const headers = ['Full Name', 'Email', 'Role', 'Status', 'Joined Date']

    const rows = filteredUsers.map((u) => [u.fullName, u.email, u.role, u.status, u.createdAt])

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

    apiPost('/api/system/exportlog', { report_type: 'accounts', format: 'CSV' }).catch(() => {})
  }

  return (
    <main className="ml-55 flex-1">
      <div className="space-y-6">

        {/* HEADER */}
        <PageHeader
          title="User Management"
          description="Manage all users in one place. Control access, assign roles, and monitor activity across your platform."
        />

        {loadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
            {loadError}
          </div>
        )}

        {/* TABS + ACTIONS */}
        <div className="flex flex-wrap items-center justify-between gap-4">

          <div className="flex gap-6 border-b border-gray-200 dark:border-white/10">
            {(['all', ...STATUS_OPTIONS] as StatusFilter[]).map((status) => (
              <button
                key={status}
                type="button"
                onClick={() => setStatusFilter(status)}
                className={`pb-3 text-sm transition ${
                  statusFilter === status
                    ? 'border-b-2 border-gray-900 font-medium text-gray-900 dark:border-white dark:text-white'
                    : 'text-gray-500 hover:text-gray-900 dark:text-white/60 dark:hover:text-white'
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
              className="px-4 py-2 rounded-lg bg-white border border-gray-200 text-gray-800 shadow-sm hover:bg-gray-50 dark:bg-white/10 dark:text-white dark:border-transparent dark:hover:bg-white/20 transition disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
            >
              Export
            </button>

            <button
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2 rounded-lg bg-[#ffb100] text-black dark:text-black font-semibold hover:brightness-105 transition shadow-sm cursor-pointer"
            >
              + Add User
            </button>
          </div>

        </div>

        {isLoading ? (
          <div className="rounded-2xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-500 dark:border-white/10 dark:bg-[#171B20] dark:text-gray-400">
            Loading users…
          </div>
        ) : (
          <UserTable
            users={filteredUsers}
            title="All System Users"
            onEdit={(user) => setEditingUser(user)}
          />
        )}

      </div>

      {/* ADD ACCOUNT MODAL */}
      {showAddModal && (
        <AddAccountModal
          roleOptions={roleOptions}
          strongPasswordPolicy={settings.strongPasswordPolicy}
          onCancel={() => setShowAddModal(false)}
          onCreated={() => {
            setShowAddModal(false)
            refreshUsers()
          }}
        />
      )}

      {/* EDIT ACCOUNT MODAL */}
      {editingUser && (
        <EditAccountModal
          user={editingUser}
          roleOptions={roleOptions}
          strongPasswordPolicy={settings.strongPasswordPolicy}
          onCancel={() => setEditingUser(null)}
          onSaved={() => {
            setEditingUser(null)
            refreshUsers()
          }}
        />
      )}

    </main>
  )
}

function AddAccountModal({
  roleOptions,
  strongPasswordPolicy,
  onCancel,
  onCreated,
}: {
  roleOptions: RoleOption[]
  strongPasswordPolicy: boolean
  onCancel: () => void
  onCreated: () => void
}) {
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    email: '',
    roleId: roleOptions[0]?.id ?? 0,
    status: 'active' as UserStatus,
    password: '',
    confirmPassword: '',
  })
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const formValid =
    form.firstName.trim() &&
    form.lastName.trim() &&
    form.email.trim() &&
    form.roleId &&
    form.password === form.confirmPassword &&
    isPasswordValid(form.password, strongPasswordPolicy)

  const handleAddUser = async () => {
    if (!formValid) return
    setIsSaving(true)
    setError(null)
    try {
      await apiPost('/api/user/accounts', {
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        email: form.email.trim(),
        password: form.password,
        confirm_password: form.confirmPassword,
        status: form.status,
        role_id: form.roleId,
      })
      onCreated()
    } catch (err) {
      setError(errorMessage(err, 'Unable to create the account.'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="relative w-full max-w-xl rounded-3xl bg-[#0D1117] p-8 shadow-xl">

        <button
          onClick={onCancel}
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
              value={form.firstName}
              onChange={(e) => setForm({ ...form, firstName: e.target.value })}
              placeholder="e.g. JUAN"
              className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
              LAST NAME
            </label>
            <input
              value={form.lastName}
              onChange={(e) => setForm({ ...form, lastName: e.target.value })}
              placeholder="e.g. CRUZ"
              className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
            />
          </div>

          <div className="col-span-2">
            <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
              EMAIL
            </label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="e.g. juan.cruz@email.com"
              className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
              ROLE
            </label>
            <select
              value={form.roleId}
              onChange={(e) => setForm({ ...form, roleId: Number(e.target.value) })}
              className={SELECT_CLASS}
            >
              {roleOptions.length === 0 && <option value={0} className="bg-[#0D1117]">No roles available</option>}
              {roleOptions.map((role) => (
                <option key={role.id} value={role.id} className="bg-[#0D1117]">{role.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
              STATUS
            </label>
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as UserStatus })}
              className={SELECT_CLASS}
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status} value={status} className="bg-[#0D1117]">
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </option>
              ))}
            </select>
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
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
              CONFIRM PASSWORD
            </label>
            <input
              type="password"
              value={form.confirmPassword}
              onChange={(e) => setForm({ ...form, confirmPassword: e.target.value })}
              className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none"
            />
          </div>
        </div>

        <p className="mt-2 text-center text-xs text-gray-500">
          {strongPasswordPolicy
            ? 'Passwords need 12+ characters with upper, lower, a number, and a symbol.'
            : 'Passwords need at least 8 characters.'}
        </p>

        {form.password &&
          form.confirmPassword &&
          form.password !== form.confirmPassword && (
            <p className="mt-2 text-center text-xs text-red-400">
              Passwords do not match.
            </p>
          )}

        {error && (
          <p className="mt-3 text-center text-sm text-red-400">{error}</p>
        )}

        <button
          onClick={handleAddUser}
          disabled={!formValid || isSaving}
          className="mx-auto mt-6 block rounded-full bg-[#ffb100] px-10 py-2.5 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSaving ? 'SAVING…' : 'SAVE CHANGES'}
        </button>

      </div>
    </div>
  )
}

function EditAccountModal({
  user,
  roleOptions,
  strongPasswordPolicy,
  onCancel,
  onSaved,
}: {
  user: User
  roleOptions: RoleOption[]
  strongPasswordPolicy: boolean
  onCancel: () => void
  onSaved: () => void
}) {
  const matchingRole = roleOptions.find((r) => r.name === user.role)

  const [form, setForm] = useState({
    firstName: user.firstName,
    lastName: user.lastName,
    email: user.email,
    roleId: matchingRole?.id ?? roleOptions[0]?.id ?? 0,
    status: user.status,
  })
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The backend's edit_account endpoint requires a new password on every
  // edit — there's no "leave unchanged" option, so this field is mandatory
  // here too (see server/app/api/user/management.py edit_account).
  const passwordValid =
    newPassword === confirmPassword && isPasswordValid(newPassword, strongPasswordPolicy)

  const handleSave = async () => {
    if (!passwordValid) return
    setIsSaving(true)
    setError(null)
    try {
      await apiPut(`/api/user/accounts/${user.id}`, {
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        email: form.email.trim(),
        role_id: form.roleId,
        status: form.status,
        password: newPassword,
        confirm_password: confirmPassword,
      })
      onSaved()
    } catch (err) {
      setError(errorMessage(err, 'Unable to update the account.'))
    } finally {
      setIsSaving(false)
    }
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

        <div className="mt-6 grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1.5 block text-sm text-gray-300">First Name</label>
            <input
              value={form.firstName}
              onChange={(e) => setForm({ ...form, firstName: e.target.value })}
              className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm text-gray-300">Last Name</label>
            <input
              value={form.lastName}
              onChange={(e) => setForm({ ...form, lastName: e.target.value })}
              className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
            />
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1.5 block text-sm text-gray-300">Email</label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm text-gray-300">Role</label>
            <select
              value={form.roleId}
              onChange={(e) => setForm({ ...form, roleId: Number(e.target.value) })}
              className={SELECT_CLASS}
            >
              {roleOptions.map((role) => (
                <option key={role.id} value={role.id} className="bg-[#0D1117]">{role.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1.5 block text-sm text-gray-300">Status</label>
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value as UserStatus })}
              className={SELECT_CLASS}
            >
              {STATUS_OPTIONS.map((status) => (
                <option key={status} value={status} className="bg-[#0D1117]">
                  {status.charAt(0).toUpperCase() + status.slice(1)}
                </option>
              ))}
            </select>
          </div>

        </div>

        <div className="mt-4 grid grid-cols-2 gap-4 rounded-xl border border-white/10 p-4">
          <div className="col-span-2 text-xs text-gray-500">
            {strongPasswordPolicy
              ? 'Saving requires setting a new password (12+ characters, upper, lower, number, symbol).'
              : 'Saving requires setting a new password (at least 8 characters).'}
          </div>
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

        {error && (
          <p className="mt-4 text-center text-sm text-red-400">{error}</p>
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
            disabled={!passwordValid || isSaving}
            className="rounded-full bg-[#ffb100] px-8 py-2.5 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>

        <p className="mt-4 text-center text-xs text-gray-500">
          The user will be signed out after changes are applied.
        </p>

      </div>
    </div>
  )
}
