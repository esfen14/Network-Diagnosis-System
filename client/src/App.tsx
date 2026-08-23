// PLEASE WALANG GAGALAW NG KAHIT ANO DITO
import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminLayout } from './components/layout/AdminLayout'
import { LoginPage } from './pages/LoginPage'
import { DashboardPage } from './pages/DashboardPage'
import { NetworkHealthPage } from './pages/NetworkHealthPage'
import { DeviceInventoryPage } from './pages/DeviceInventoryPage'
// import { TopologyPage } from './pages/TopologyPage' // hidden for now
import { ReportsPage } from './pages/ReportsPage'
import { SystemLogsPage } from './pages/SystemLogsPage'
import { ManageAccountsPage } from './pages/ManageAccountsPage'
import { PluginsPage } from './pages/PluginsPage'
import { SettingsPage } from './pages/SettingsPage'
export default function App() {
  return (
    <Routes>
      
      <Route
        path="/login"
        element={<LoginPage />}
      />
      <Route
        path="/"
        element={<AdminLayout />}
      >
        <Route
          index
          element={
            <Navigate
              to="/login"
              replace
            />
          }
        />
        <Route
          path="dashboard"
          element={<DashboardPage />}
        />
        <Route
          path="network-health"
          element={<NetworkHealthPage />}
        />
        <Route
          path="device-inventory"
          element={<DeviceInventoryPage />}
        />

        {/* Hidden for now — re-enable when Topology View is ready
        <Route
          path="topology"
          element={<TopologyPage />}
        />
        */}

        <Route
          path="reports"
          element={<ReportsPage />}
        />
        <Route
          path="system-logs"
          element={<SystemLogsPage />}
        />
        <Route
          path="accounts"
          element={<ManageAccountsPage />}
        />
        <Route
          path="plugins"
          element={<PluginsPage />}
        />
        <Route
          path="settings"
          element={<SettingsPage />}
        />
      </Route>
      {/* Unknown routes */}
      <Route
        path="*"
        element={
          <Navigate
            to="/login"
            replace
          />
        }
      />
    </Routes>
  )
}
