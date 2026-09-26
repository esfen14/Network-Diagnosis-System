// Mirrors the Role model exposed by server/app/api/user/management.py.

export type Permission = {
  id: number
  name: string
}

export type Role = {
  id: number
  name: string
  description: string
  isActive: boolean
  createdAt: string
}

export type RoleDetail = Role & {
  permissions: Permission[]
}

type RoleApiRecord = {
  id: number
  name: string
  description: string
  is_active: boolean
  created_at: string
}

type RoleDetailApiRecord = {
  id: number
  name: string
  description: string
  is_active: boolean
  permissions: Permission[]
}

export function fromRoleRecord(record: RoleApiRecord): Role {
  return {
    id: record.id,
    name: record.name,
    description: record.description,
    isActive: record.is_active,
    createdAt: record.created_at,
  }
}

export function fromRoleDetailRecord(record: RoleDetailApiRecord): RoleDetail {
  return {
    id: record.id,
    name: record.name,
    description: record.description,
    isActive: record.is_active,
    createdAt: '',
    permissions: record.permissions,
  }
}
