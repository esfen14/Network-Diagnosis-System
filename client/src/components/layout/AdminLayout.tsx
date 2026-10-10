import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { Sidebar } from './Sidebar'
import { SessionTimeoutWatcher } from './SessionTimeoutWatcher'
import { MaintenanceBanner } from './MaintenanceBanner'
import { PageAccessGuard } from './PageAccessGuard'
import { SystemSettingsProvider } from '../../contexts/SystemSettingsContext'
import { CurrentUserProvider, useCurrentUser } from '../../contexts/CurrentUserContext'
import { ForcePasswordChange } from './ForcePasswordChange'
import { FirstRunSetup } from './FirstRunSetup'

function LayoutBody() {
  const { user } = useCurrentUser()

  if (user?.needsSetup) {
    return (
      <>
        <SessionTimeoutWatcher />
        <FirstRunSetup />
      </>
    )
  }

  if (user?.mustChangePassword) {
    return (
      <>
        <SessionTimeoutWatcher />
        <ForcePasswordChange />
      </>
    )
  }

  return (
    <>
      <SessionTimeoutWatcher />
      <div className="admin-bg flex min-h-screen">
        <Sidebar />

        <main className="admin-bg flex min-h-screen flex-1 flex-col min-w-0">
          <div className="ml-[215px]">
            <Header />
          </div>

          <div className="flex-1 overflow-x-auto overflow-y-auto px-4 pb-8 min-w-0">
            <MaintenanceBanner />
            <PageAccessGuard>
              <Outlet />
            </PageAccessGuard>
          </div>
        </main>
      </div>
    </>
  )
}

export function AdminLayout() {
  return (
    <CurrentUserProvider>
      <SystemSettingsProvider>
        <LayoutBody />
      </SystemSettingsProvider>
    </CurrentUserProvider>
  )
}
