import { useEffect, useMemo, useState } from 'react'
import { ArrowUpDown, Filter, Pencil, Search, X } from 'lucide-react'
import { PageHeader } from '../components/shared/PageHeader'
import { apiGet, apiPost, apiPut, errorMessage } from '../lib/api'
import {
  fromRoleDetailRecord,
  fromRoleRecord,
  type Permission,
  type Role,
  type RoleDetail,
} from '../types/role'

type StatusFilter = 'all' | 'active' | 'inactive'

function formatDate(iso: string) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

async function fetchRoles(): Promise<Role[]> {
  const data = await apiGet<{ items: Parameters<typeof fromRoleRecord>[0][] }>(
    '/api/user/roles?per_page=100'
  )
  return data.items.map(fromRoleRecord)
}

async function fetchPermissionOptions(): Promise<Permission[]> {
  const data = await apiGet<{ items: Permission[] }>('/api/user/permissions/options')
  return data.items
}

async function fetchRoleDetail(id: number): Promise<RoleDetail> {
  const data = await apiGet<Parameters<typeof fromRoleDetailRecord>[0]>(`/api/user/roles/${id}`)
  return fromRoleDetailRecord(data)
}

export function ManageRolesPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [allRoles, setAllRoles] = useState<Role[]>([])
  const [permissionOptions, setPermissionOptions] = useState<Permission[]>([])

  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [showAddModal, setShowAddModal] = useState(false)
  const [editingRole, setEditingRole] = useState<Role | null>(null)
  const [togglingId, setTogglingId] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setLoadError(null)
      try {
        const [roles, permissions] = await Promise.all([fetchRoles(), fetchPermissionOptions()])
        if (cancelled) return
        setAllRoles(roles)
        setPermissionOptions(permissions)
      } catch (err) {
        if (cancelled) return
        setLoadError(errorMessage(err, 'Unable to load roles.'))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  async function refreshRoles() {
    try {
      setAllRoles(await fetchRoles())
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to refresh roles.'))
    }
  }

  const filteredRoles = useMemo(() => {
    let result = allRoles
    if (statusFilter !== 'all') {
      result = result.filter((r) => (statusFilter === 'active' ? r.isActive : !r.isActive))
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (r) => r.name.toLowerCase().includes(q) || r.description.toLowerCase().includes(q)
      )
    }
    return result
  }, [allRoles, statusFilter, searchQuery])

  async function toggleStatus(role: Role) {
    setTogglingId(role.id)
    try {
      await apiPut(`/api/user/roles/${role.id}/status`)
      await refreshRoles()
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to change role status.'))
    } finally {
      setTogglingId(null)
    }
  }

  return (
    <main className="ml-[220px] flex-1">
      <div className="space-y-6">
        <PageHeader
          title="Manage Roles"
          description="Define roles and permissions for system users."
        />

        {loadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
            {loadError}
          </div>
        )}

        {/* Filter tabs */}
        <div className="flex gap-6 border-b border-gray-200 dark:border-white/10">
          {(['all', 'active', 'inactive'] as StatusFilter[]).map((status) => (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
              className={`pb-3 text-sm capitalize transition ${
                statusFilter === status
                  ? 'border-b-2 border-gray-900 font-medium text-gray-900 dark:border-white dark:text-white'
                  : 'text-gray-500 hover:text-gray-900 dark:text-white/60 dark:hover:text-white'
              }`}
            >
              {status}
            </button>
          ))}
        </div>

        {/* Table card */}
        <div className="overflow-hidden rounded-2xl bg-white border border-gray-200 shadow-sm dark:bg-[#171B20] dark:border-white/10">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-gray-200 p-4 dark:border-white/10">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">All System Roles</h2>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowAddModal(true)}
                className="px-4 py-2 rounded-lg bg-[#ffb100] text-black font-semibold text-sm hover:brightness-105 transition"
              >
                + Add Role
              </button>
              <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-white/10 dark:bg-[#0D1117]">
                <Search className="h-4 w-4 text-gray-500 dark:text-gray-400" />
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search"
                  className="bg-transparent text-sm text-gray-900 placeholder:text-gray-500 outline-none dark:text-white dark:placeholder:text-gray-400"
                />
              </div>
              <button
                type="button"
                className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
                aria-label="Filter"
              >
                <Filter className="h-4 w-4" />
              </button>
              <button
                type="button"
                className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white"
                aria-label="Sort"
              >
                <ArrowUpDown className="h-4 w-4" />
              </button>
            </div>
          </div>

          {isLoading ? (
            <div className="p-8 text-center text-sm text-gray-500 dark:text-gray-400">Loading roles…</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-400">
                    <th className="px-4 py-3 font-normal">Role Name</th>
                    <th className="px-4 py-3 font-normal">Description</th>
                    <th className="px-4 py-3 font-normal">Status</th>
                    <th className="px-4 py-3 font-normal">Created</th>
                    <th className="px-4 py-3 font-normal">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRoles.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                        No roles match your search or filter
                      </td>
                    </tr>
                  ) : (
                    filteredRoles.map((role) => (
                      <tr key={role.id} className="border-b border-gray-100 transition hover:bg-gray-50 dark:border-white/5 dark:hover:bg-white/5">
                        <td className="px-4 py-3 text-gray-900 dark:text-white">{role.name}</td>
                        <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{role.description || '—'}</td>
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            onClick={() => toggleStatus(role)}
                            disabled={togglingId === role.id}
                            className={`rounded-full px-2.5 py-1 text-xs font-medium capitalize disabled:opacity-50 ${
                              role.isActive
                                ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                                : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                            }`}
                          >
                            {togglingId === role.id ? '…' : role.isActive ? 'Active' : 'Inactive'}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{formatDate(role.createdAt)}</td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => setEditingRole(role)}
                            className="text-gray-400 hover:text-gray-700 dark:text-gray-400 dark:hover:text-white"
                            aria-label="Edit role"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
            <span>Showing {filteredRoles.length} of {allRoles.length} roles</span>
          </div>
        </div>
      </div>

      {/* ADD ROLE MODAL */}
      {showAddModal && (
        <AddRoleModal
          permissionOptions={permissionOptions}
          onCancel={() => setShowAddModal(false)}
          onCreated={() => {
            setShowAddModal(false)
            refreshRoles()
          }}
        />
      )}

      {/* EDIT ROLE MODAL */}
      {editingRole && (
        <EditRoleModal
          role={editingRole}
          permissionOptions={permissionOptions}
          onCancel={() => setEditingRole(null)}
          onSaved={() => {
            setEditingRole(null)
            refreshRoles()
          }}
        />
      )}
    </main>
  )
}

function AddRoleModal({
  permissionOptions,
  onCancel,
  onCreated,
}: {
  permissionOptions: Permission[]
  onCancel: () => void
  onCreated: () => void
}) {
  const [form, setForm] = useState({
    roleName: '',
    description: '',
    permissions: [] as number[],
  })
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const formValid = form.roleName.trim().length > 0

  const togglePermission = (id: number) => {
    setForm((prev) => ({
      ...prev,
      permissions: prev.permissions.includes(id)
        ? prev.permissions.filter((p) => p !== id)
        : [...prev.permissions, id],
    }))
  }

  const handleAddRole = async () => {
    if (!formValid) return
    setIsSaving(true)
    setError(null)
    try {
      await apiPost('/api/user/roles', {
        role_name: form.roleName.trim(),
        description: form.description.trim(),
        permissions: form.permissions,
      })
      onCreated()
    } catch (err) {
      setError(errorMessage(err, 'Unable to create the role.'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="relative w-full max-w-xl rounded-3xl bg-white p-8 shadow-xl">
        <button
          onClick={onCancel}
          className="absolute right-5 top-5 text-gray-400 hover:text-gray-600"
        >
          <X className="h-5 w-5" />
        </button>

        <h2 className="text-center text-xl font-semibold text-gray-900">
          Role Info
        </h2>

        <div className="mt-6 grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-500">
              ROLE NAME
            </label>
            <input
              value={form.roleName}
              onChange={(e) => setForm({ ...form, roleName: e.target.value })}
              placeholder="e.g. Supervisor"
              className="w-full rounded-full border border-gray-300 bg-white px-4 py-2.5 text-sm text-gray-900 outline-none focus:border-gray-500 placeholder:text-gray-400"
            />
          </div>

          <div className="col-span-2">
            <label className="mb-1.5 block text-xs font-medium tracking-wide text-gray-500">
              DESCRIPTION
            </label>
            <textarea
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="Short description of this role"
              rows={2}
              className="w-full rounded-2xl border border-gray-300 bg-white px-4 py-2.5 text-sm text-gray-900 outline-none focus:border-gray-500 placeholder:text-gray-400"
            />
          </div>
        </div>

        <div className="my-6 border-t border-gray-200" />

        <h2 className="text-center text-xl font-semibold text-gray-900">
          Permission
        </h2>

        <div className="mt-4 max-h-56 overflow-y-auto rounded-2xl border border-gray-200">
          {permissionOptions.length === 0 && (
            <p className="px-4 py-3 text-sm text-gray-500">No permissions available.</p>
          )}
          {permissionOptions.map((perm, i) => (
            <label
              key={perm.id}
              className={`flex cursor-pointer items-center justify-between px-4 py-3 text-sm text-gray-700 hover:bg-gray-50 ${
                i !== permissionOptions.length - 1 ? 'border-b border-gray-200' : ''
              }`}
            >
              <span>{perm.name}</span>
              <input
                type="checkbox"
                checked={form.permissions.includes(perm.id)}
                onChange={() => togglePermission(perm.id)}
                className="h-4 w-4 rounded border-gray-300 accent-[#ffb100]"
              />
            </label>
          ))}
        </div>

        {error && <p className="mt-3 text-center text-sm text-red-600">{error}</p>}

        <button
          onClick={handleAddRole}
          disabled={!formValid || isSaving}
          className="mx-auto mt-6 block rounded-full bg-[#ffb100] px-10 py-2.5 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSaving ? 'SAVING…' : 'SAVE CHANGES'}
        </button>
      </div>
    </div>
  )
}

function EditRoleModal({
  role,
  permissionOptions,
  onCancel,
  onSaved,
}: {
  role: Role
  permissionOptions: Permission[]
  onCancel: () => void
  onSaved: () => void
}) {
  const [form, setForm] = useState({ name: role.name, description: role.description })
  const [permissions, setPermissions] = useState<number[]>([])
  const [isLoadingDetail, setIsLoadingDetail] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchRoleDetail(role.id)
      .then((detail) => {
        if (cancelled) return
        setForm({ name: detail.name, description: detail.description })
        setPermissions(detail.permissions.map((p) => p.id))
      })
      .catch((err) => {
        if (cancelled) return
        setError(errorMessage(err, 'Unable to load role details.'))
      })
      .finally(() => {
        if (!cancelled) setIsLoadingDetail(false)
      })
    return () => {
      cancelled = true
    }
  }, [role.id])

  const togglePermission = (id: number) => {
    setPermissions((prev) => (prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]))
  }

  const handleSave = async () => {
    setIsSaving(true)
    setError(null)
    try {
      await apiPut(`/api/user/roles/${role.id}`, {
        name: form.name.trim(),
        description: form.description.trim(),
        permissions,
      })
      onSaved()
    } catch (err) {
      setError(errorMessage(err, 'Unable to update the role.'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="relative w-full max-w-2xl rounded-3xl bg-white p-8 shadow-xl">
        <button
          onClick={onCancel}
          className="absolute right-5 top-5 text-gray-400 hover:text-gray-600"
        >
          <X className="h-5 w-5" />
        </button>

        <h2 className="text-xl font-semibold text-gray-900">Edit Role</h2>
        <p className="mt-1 text-sm text-gray-500">
          Update role information and assigned permissions.
        </p>

        {isLoadingDetail ? (
          <p className="mt-6 text-sm text-gray-500">Loading role details…</p>
        ) : (
          <>
            <div className="mt-6 grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1.5 block text-sm text-gray-600">Role Name</label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full rounded-full border border-gray-300 bg-white px-4 py-2.5 text-sm text-gray-900 outline-none focus:border-gray-500"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm text-gray-600">Description</label>
                <input
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="w-full rounded-full border border-gray-300 bg-white px-4 py-2.5 text-sm text-gray-900 outline-none focus:border-gray-500"
                />
              </div>
            </div>

            <h3 className="mt-6 text-sm font-medium text-gray-700">Permissions</h3>
            <div className="mt-2 max-h-56 overflow-y-auto rounded-2xl border border-gray-200">
              {permissionOptions.map((perm, i) => (
                <label
                  key={perm.id}
                  className={`flex cursor-pointer items-center justify-between px-4 py-3 text-sm text-gray-700 hover:bg-gray-50 ${
                    i !== permissionOptions.length - 1 ? 'border-b border-gray-200' : ''
                  }`}
                >
                  <span>{perm.name}</span>
                  <input
                    type="checkbox"
                    checked={permissions.includes(perm.id)}
                    onChange={() => togglePermission(perm.id)}
                    className="h-4 w-4 rounded border-gray-300 accent-[#ffb100]"
                  />
                </label>
              ))}
            </div>

            {error && <p className="mt-4 text-center text-sm text-red-600">{error}</p>}

            <div className="mt-6 flex justify-center gap-3">
              <button
                onClick={handleSave}
                disabled={isSaving || !form.name.trim()}
                className="rounded-full bg-[#ffb100] px-8 py-2.5 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSaving ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
