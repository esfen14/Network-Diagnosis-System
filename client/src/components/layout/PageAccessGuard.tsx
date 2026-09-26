import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useCurrentUser } from '../../contexts/CurrentUserContext'
import { canAccessPage, firstAccessiblePage } from '../../lib/pageAccess'

// Redirects away from a page the user's role can't access (for example a
// bookmarked URL), to the first page they can open.
export function PageAccessGuard({ children }: { children: ReactNode }) {
  const { user, isLoading } = useCurrentUser()
  const { pathname } = useLocation()

  if (isLoading) return null

  // No user means the session ended; SessionTimeoutWatcher redirects to login.
  if (!user) return null

  if (!canAccessPage(pathname, user.permissions)) {
    return <Navigate to={firstAccessiblePage(user.permissions)} replace />
  }

  return <>{children}</>
}
