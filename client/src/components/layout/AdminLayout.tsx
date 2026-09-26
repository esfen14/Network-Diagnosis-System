import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { Sidebar } from './Sidebar'
import { SessionTimeoutWatcher } from './SessionTimeoutWatcher'
import { MaintenanceBanner } from './MaintenanceBanner'
import { PageAccessGuard } from './PageAccessGuard'
import { SystemSettingsProvider } from '../../contexts/SystemSettingsContext'
import { CurrentUserProvider } from '../../contexts/CurrentUserContext'

export function AdminLayout() {
  return (
    <CurrentUserProvider>
      <SystemSettingsProvider>
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
      </SystemSettingsProvider>
    </CurrentUserProvider>
  )
}
