import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

// The signed-in user and their role's permissions, from /api/user/me.
// Loaded once by AdminLayout and refreshed whenever the tab regains focus,
// so a role change made by an admin applies without logging out.

export type CurrentUser = {
  firstName: string
  lastName: string
  email: string
  role: string
  permissions: string[]
}

type CurrentUserContextValue = {
  user: CurrentUser | null
  isLoading: boolean
  hasPermission: (permission: string) => boolean
}

const CurrentUserContext = createContext<CurrentUserContextValue | undefined>(undefined)

async function fetchCurrentUser(): Promise<CurrentUser> {
  const res = await fetch('/api/user/me', { credentials: 'include' })
  if (!res.ok) {
    throw new Error(`Unable to load current user (${res.status})`)
  }

  const body = await res.json()
  const data = body.data ?? body

  return {
    firstName: data.first_name,
    lastName: data.last_name,
    email: data.email,
    role: data.role,
    permissions: Array.isArray(data.permissions) ? data.permissions : [],
  }
}

export function CurrentUserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    const loadUser = () => {
      fetchCurrentUser()
        .then((loaded) => {
          if (!cancelled) setUser(loaded)
        })
        .catch((error) => {
          // A 401 is handled by SessionTimeoutWatcher, which sends the user to login.
          console.error('Unable to load current user:', error)
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false)
        })
    }

    const handleVisible = () => {
      if (document.visibilityState === 'visible') {
        loadUser()
      }
    }

    loadUser()
    document.addEventListener('visibilitychange', handleVisible)
    window.addEventListener('focus', handleVisible)

    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', handleVisible)
      window.removeEventListener('focus', handleVisible)
    }
  }, [])

  const hasPermission = useCallback(
    (permission: string) => user?.permissions.includes(permission) ?? false,
    [user]
  )

  return (
    <CurrentUserContext.Provider value={{ user, isLoading, hasPermission }}>
      {children}
    </CurrentUserContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useCurrentUser() {
  const context = useContext(CurrentUserContext)
  if (!context) {
    throw new Error('useCurrentUser must be used inside CurrentUserProvider')
  }
  return context
}
