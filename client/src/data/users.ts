// USERS DATA (fixed status casing for consistency)

export type UserStatus = 'active' | 'inactive' | 'locked' | 'suspended'

export type User = {
  id: string
  fullName: string
  userId: string
  username: string
  status: UserStatus
  joinedDate: string
  lastActive: string
  role?: string
}

export const users: User[] = [
  {
    id: 'U-001',
    fullName: 'Marie Santos',
    userId: '93872jp01a',
    username: 'marie092',
    status: 'active',
    joinedDate: 'Oct 23, 2025',
    lastActive: '1 minute ago',
    role: 'Admin',
  },
  {
    id: 'U-002',
    fullName: 'John Cruz',
    userId: '8390dhy625',
    username: 'cruz_john',
    status: 'inactive',
    joinedDate: 'Oct 23, 2025',
    lastActive: '1 day ago',
    role: 'User',
  },
  {
    id: 'U-003',
    fullName: 'Michael Gonzales',
    userId: '093jwi023l',
    username: 'micl_admin',
    status: 'locked',
    joinedDate: 'Oct 22, 2025',
    lastActive: '4 days ago',
    role: 'Admin',
  },
  {
    id: 'U-004',
    fullName: 'Chloe Baltazar',
    userId: '38ud6389ks',
    username: 'chloehh',
    status: 'active',
    joinedDate: 'Oct 20, 2025',
    lastActive: '2 minutes ago',
    role: 'User',
  },
  {
    id: 'U-005',
    fullName: 'Marco Gomez',
    userId: '37290383id',
    username: 'admarco',
    status: 'suspended',
    joinedDate: 'Oct 19, 2025',
    lastActive: '1 week ago',
    role: 'User',
  },
  {
    id: 'U-006',
    fullName: 'Ella Dela Cruz',
    userId: '3820dki304',
    username: 'belle_delcz',
    status: 'active',
    joinedDate: 'Oct 10, 2025',
    lastActive: '1 hour ago',
    role: 'User',
  },
  {
    id: 'U-007',
    fullName: 'Lucas Mitchell',
    userId: '32894jsgcr',
    username: 'lucamich',
    status: 'active',
    joinedDate: 'Oct 6, 2025',
    lastActive: '4 hours ago',
    role: 'User',
  },
  {
    id: 'U-008',
    fullName: 'Mark Santos',
    userId: '83290ka8yd',
    username: 'marksants32',
    status: 'locked',
    joinedDate: 'Sept 21, 2025',
    lastActive: '1 month ago',
    role: 'Admin',
  },
  {
    id: 'U-009',
    fullName: 'Nicholas Aguirre',
    userId: '34820dk38d',
    username: 'nicolass009',
    status: 'suspended',
    joinedDate: 'Sept 9, 2025',
    lastActive: '3 hours ago',
    role: 'User',
  },
  {
    id: 'U-010',
    fullName: 'Mia Nicdao',
    userId: '49437jdw3e',
    username: 'mianaddiin',
    status: 'inactive',
    joinedDate: 'Sept 8, 2025',
    lastActive: '1 month ago',
    role: 'User',
  },
  {
    id: 'U-011',
    fullName: 'Joshua Vilar',
    userId: '48950ip39q',
    username: 'joshh_min',
    status: 'active',
    joinedDate: 'Sept 2, 2025',
    lastActive: '15 minutes ago',
    role: 'Admin',
  },
]