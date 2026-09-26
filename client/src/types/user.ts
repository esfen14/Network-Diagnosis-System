// Mirrors the User model exposed by server/app/api/user/management.py.
// Status values match server/app/system_models.py's UserStatus enum —
// there is no "locked" status on the backend, only active/inactive/suspended.

export type UserStatus = 'active' | 'inactive' | 'suspended'

export type User = {
  id: number
  firstName: string
  lastName: string
  fullName: string
  email: string
  role: string
  status: UserStatus
  createdAt: string
  updatedAt: string
}

export type RoleOption = {
  id: number
  name: string
}

type AccountApiRecord = {
  id: number
  first_name: string
  last_name: string
  email: string
  role: string
  status: string
  created_at: string
  updated_at: string
}

export function fromAccountRecord(record: AccountApiRecord): User {
  return {
    id: record.id,
    firstName: record.first_name,
    lastName: record.last_name,
    fullName: `${record.first_name} ${record.last_name}`.trim(),
    email: record.email,
    role: record.role,
    status: record.status.toLowerCase() as UserStatus,
    createdAt: record.created_at,
    updatedAt: record.updated_at,
  }
}
