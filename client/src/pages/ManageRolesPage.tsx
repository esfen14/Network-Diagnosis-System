import { useMemo, useState } from 'react'
import { ArrowUpDown, Filter, Pencil, Search, X } from 'lucide-react'
import { PageHeader } from '../components/shared/PageHeader'

type RoleType = 'admin' | 'manager' | 'staff'
type RoleFilter = 'all' | RoleType

type Role = {
  id: string
  fullName: string
  roleId: string
  username: string
  roleType: RoleType
  assignedDate: string
  lastCommit: string
}

const initialRoles: Role[] = [
  { id: '1', fullName: 'Rafael Esfen', roleId: '10ad4471', username: 'esfen14', roleType: 'admin', assignedDate: '2025-10-20', lastCommit: '2 minutes ago' },
  { id: '2', fullName: 'Karell Ramos', roleId: '20mg8823', username: 'karell_r', roleType: 'admin', assignedDate: '2025-10-10', lastCommit: '1 hour ago' },
  { id: '3', fullName: 'Chloe Baltazar', roleId: '38ud6389', username: 'chloehh', roleType: 'manager', assignedDate: '2025-10-23', lastCommit: '1 day ago' },
  { id: '4', fullName: 'Joshua Vilar', roleId: '48950ip3', username: 'joshh_min', roleType: 'manager', assignedDate: '2025-09-02', lastCommit: '15 minutes ago' },
  { id: '5', fullName: 'Lucas Mitchell', roleId: '32894jsg', username: 'lucamich', roleType: 'staff', assignedDate: '2025-10-06', lastCommit: '4 hours ago' },
  { id: '6', fullName: 'Marie Santos', roleId: '93872jp0', username: 'marie092', roleType: 'staff', assignedDate: '2025-10-23', lastCommit: '1 minute ago' },
]

const permissionsList = [
  'View Dashboard',
  'Manage Devices',
  'Manage Users',
  'Manage Roles',
  'View Reports',
  'Export Data',
  'System Settings',
]

function generateRoleId() {
  return Array.from({ length: 8 }, () => Math.floor(Math.random() * 16).toString(16)).join('')
}

const roleBadgeStyle: Record<string, string> = {
  admin: 'bg-red-500/20 text-red-400',
  manager: 'bg-amber-500/20 text-amber-400',
  staff: 'bg-emerald-500/20 text-emerald-400',
}
const defaultBadgeStyle = 'bg-blue-500/20 text-blue-400'

export function ManageRolesPage() {
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('all')
  const [allRoles, setAllRoles] = useState<Role[]>(initialRoles)
  const [searchQuery, setSearchQuery] = useState('')

  const [showAddModal, setShowAddModal] = useState(false)
  const [editingRole, setEditingRole] = useState<Role | null>(null)

  const [newRole, setNewRole] = useState({
    fullName: '',
    username: '',
    roleId: generateRoleId(),
    roleName: '',
    description: '',
    permissions: [] as string[],
  })

  const filteredRoles = useMemo(() => {
    let result = roleFilter === 'all' ? allRoles : allRoles.filter((r) => r.roleType === roleFilter)
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (r) => r.fullName.toLowerCase().includes(q) || r.username.toLowerCase().includes(q)
      )
    }
    return result
  }, [allRoles, roleFilter, searchQuery])

  const resetAddForm = () => {
    setNewRole({
      fullName: '',
      username: '',
      roleId: generateRoleId(),
      roleName: '',
      description: '',
      permissions: [],
    })
  }

  const closeAddModal = () => {
    setShowAddModal(false)
    resetAddForm()
  }

  const togglePermission = (perm: string) => {
    setNewRole((prev) => ({
      ...prev,
      permissions: prev.permissions.includes(perm)
        ? prev.permissions.filter((p) => p !== perm)
        : [...prev.permissions, perm],
    }))
  }

  const addFormValid = newRole.fullName.trim() && newRole.username.trim() && newRole.roleName.trim()

  const handleAddRole = () => {
    if (!addFormValid) return

    const today = new Date().toISOString().split('T')[0]

    const role: Role = {
      id: newRole.roleId,
      fullName: newRole.fullName.trim(),
      roleId: newRole.roleId,
      username: newRole.username.trim(),
      roleType: newRole.roleName.trim().toLowerCase() as RoleType,
      assignedDate: today,
      lastCommit: 'Never',
    }

    setAllRoles((prev) => [...prev, role])
    closeAddModal()
  }

  const handleSaveEdit = (updated: Role) => {
    setAllRoles((prev) => prev.map((r) => (r.id === updated.id ? updated : r)))
    setEditingRole(null)
  }

  return (
    <main className="ml-[220px] flex-1">
      <div className="space-y-6">
        <PageHeader
          title="Manage Roles"
          description="Define roles and permissions for system users."
        />

        <div className="flex flex-wrap items-center gap-2">
          {(['all', 'admin', 'manager', 'staff'] as RoleFilter[]).map((role) => (
            <button
              key={role}
              onClick={() => setRoleFilter(role)}
              className={`px-4 py-2 rounded-lg text-sm capitalize transition ${
                roleFilter === role
                  ? 'bg-white text-black'
                  : 'bg-white/10 text-gray-300 hover:bg-white/20'
              }`}
            >
              {role}
            </button>
          ))}
        </div>

        <div className="rounded-3xl bg-[#0D1117] p-6 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h2 className="text-lg font-semibold text-white">All System Roles</h2>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowAddModal(true)}
                className="px-4 py-2 rounded-lg bg-[#ffb100] text-black text-sm font-medium"
              >
                + Add Role
              </button>
              <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3 py-2">
                <Search className="h-4 w-4 text-gray-400" />
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search"
                  className="bg-transparent text-sm text-white placeholder:text-gray-400 outline-none"
                />
              </div>
              <button
                type="button"
                className="rounded-2xl border border-white/10 p-2 text-gray-400 hover:bg-white/5"
                aria-label="Filter"
              >
                <Filter className="h-4 w-4" />
              </button>
              <button
                type="button"
                className="rounded-2xl border border-white/10 p-2 text-gray-400 hover:bg-white/5"
                aria-label="Sort"
              >
                <ArrowUpDown className="h-4 w-4" />
              </button>
            </div>
          </div>

          <div className="mt-6 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-xs uppercase text-gray-500">
                  <th className="pb-3 pr-4 font-medium">Full Name</th>
                  <th className="pb-3 pr-4 font-medium">Role ID</th>
                  <th className="pb-3 pr-4 font-medium">Username</th>
                  <th className="pb-3 pr-4 font-medium">Role</th>
                  <th className="pb-3 pr-4 font-medium">Assigned Date</th>
                  <th className="pb-3 pr-4 font-medium">Last Commit</th>
                  <th className="pb-3 pr-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRoles.map((role) => (
                  <tr key={role.id} className="border-t border-white/10">
                    <td className="py-3 pr-4 font-medium text-white">{role.fullName}</td>
                    <td className="py-3 pr-4 text-gray-400">{role.roleId}</td>
                    <td className="py-3 pr-4 text-gray-400">{role.username}</td>
                    <td className="py-3 pr-4">
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize ${
                          roleBadgeStyle[role.roleType] ?? defaultBadgeStyle
                        }`}
                      >
                        {role.roleType}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-gray-400">{role.assignedDate}</td>
                    <td className="py-3 pr-4 text-gray-400">{role.lastCommit}</td>
                    <td className="py-3 pr-4">
                      <button
                        onClick={() => setEditingRole(role)}
                        className="text-gray-500 hover:text-gray-300"
                        aria-label="Edit role"
                      >
                        <Pencil className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-4 text-right text-sm text-gray-500">
            Showing {filteredRoles.length} of {allRoles.length} roles
          </p>
        </div>
      </div>

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
              Role Info
            </h2>

            <div className="mt-6 grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  FULL NAME
                </label>
                <input
                  value={newRole.fullName}
                  onChange={(e) => setNewRole({ ...newRole, fullName: e.target.value })}
                  placeholder="e.g. JUAN CRUZ"
                  className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  USERNAME
                </label>
                <input
                  value={newRole.username}
                  onChange={(e) => setNewRole({ ...newRole, username: e.target.value })}
                  placeholder="Create a valid username."
                  className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  ROLE NAME
                </label>
                <input
                  value={newRole.roleName}
                  onChange={(e) => setNewRole({ ...newRole, roleName: e.target.value })}
                  placeholder="e.g. Supervisor"
                  className="w-full rounded-full bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  ROLE ID
                </label>
                <input
                  value={newRole.roleId}
                  disabled
                  className="w-full rounded-full bg-white/10 px-4 py-2.5 text-sm text-gray-400 outline-none"
                />
              </div>

              <div className="col-span-2">
                <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-400">
                  DESCRIPTION
                </label>
                <textarea
                  value={newRole.description}
                  onChange={(e) => setNewRole({ ...newRole, description: e.target.value })}
                  placeholder="Short description of this role"
                  rows={2}
                  className="w-full rounded-2xl bg-white px-4 py-2.5 text-sm text-gray-900 outline-none placeholder:text-gray-400"
                />
              </div>
            </div>

            <div className="my-6 border-t border-white/10" />

            <h2 className="text-center text-xl font-semibold text-white">
              Permission
            </h2>

            <div className="mt-4 max-h-56 overflow-y-auto rounded-2xl border border-white/10">
              {permissionsList.map((perm, i) => (
                <label
                  key={perm}
                  className={`flex cursor-pointer items-center justify-between px-4 py-3 text-sm text-gray-200 ${
                    i !== permissionsList.length - 1 ? 'border-b border-white/10' : ''
                  }`}
                >
                  <span>{perm}</span>
                  <input
                    type="checkbox"
                    checked={newRole.permissions.includes(perm)}
                    onChange={() => togglePermission(perm)}
                    className="h-4 w-4 rounded border-white/30 bg-transparent accent-[#ffb100]"
                  />
                </label>
              ))}
            </div>

            <button
              onClick={handleAddRole}
              disabled={!addFormValid}
              className="mx-auto mt-6 block rounded-full bg-[#ffb100] px-10 py-2.5 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
            >
              SAVE CHANGES
            </button>
          </div>
        </div>
      )}

      {editingRole && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="relative w-full max-w-2xl rounded-3xl bg-[#0D1117] p-8 shadow-xl">
            <button
              onClick={() => setEditingRole(null)}
              className="absolute right-5 top-5 text-gray-500 hover:text-gray-300"
            >
              <X className="h-5 w-5" />
            </button>

            <h2 className="text-xl font-semibold text-white">Edit Role</h2>
            <p className="mt-1 text-sm text-gray-400">
              Update user information and assigned role.
            </p>

            <EditRoleForm role={editingRole} onSave={handleSaveEdit} />
          </div>
        </div>
      )}
    </main>
  )
}

function EditRoleForm({
  role,
  onSave,
}: {
  role: Role
  onSave: (updated: Role) => void
}) {
  const [form, setForm] = useState({
    fullName: role.fullName,
    username: role.username,
    roleType: role.roleType,
  })

  const handleSave = () => {
    onSave({
      ...role,
      fullName: form.fullName,
      username: form.username,
      roleType: form.roleType,
    })
  }

  return (
    <>
      <div className="mt-6 grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1.5 block text-sm text-gray-300">Full Name</label>
          <input
            value={form.fullName}
            onChange={(e) => setForm({ ...form, fullName: e.target.value })}
            className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
          />
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

      <div className="mt-4">
        <label className="mb-1.5 block text-sm text-gray-300">Role Name</label>
        <input
          value={form.roleType}
          onChange={(e) => setForm({ ...form, roleType: e.target.value as RoleType })}
          className="w-full rounded-full border border-white/20 bg-transparent px-4 py-2.5 text-sm text-white outline-none focus:border-white/40"
        />
      </div>

      <div className="mt-4">
        <label className="mb-1.5 block text-sm text-gray-300">Role ID</label>
        <input
          value={role.roleId}
          disabled
          className="w-full rounded-full border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-gray-500 outline-none"
        />
      </div>

      <div className="mt-6 flex justify-center gap-3">
        <button
          onClick={handleSave}
          className="rounded-full bg-[#ffb100] px-8 py-2.5 text-sm font-semibold text-black"
        >
          Save Changes
        </button>
      </div>
    </>
  )
}