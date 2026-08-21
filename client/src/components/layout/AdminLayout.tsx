import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { Sidebar } from './Sidebar'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'

export function AdminLayout() {
  const { settings } = useSystemSettings()

  const isLight = settings.theme === 'light'

  return (
    <div
      className={`flex min-h-screen ${
        isLight
          ? 'bg-[#f5f6f8]'
          : 'bg-pinpoint-sidebar'
      }`}
    >
      <Sidebar />

      <main
        className={`flex min-h-screen flex-1 flex-col ${
          isLight
            ? 'bg-[#f5f6f8]'
            : 'bg-pinpoint-dark'
        }`}
      >
        <div className="ml-[215px]">
          <Header />
        </div>

        <div className="flex-1 overflow-y-auto px-4 pb-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}