import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminLayout } from './components/layout/AdminLayout'

import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { DeviceInventoryPage } from './pages/DeviceInventoryPage'
import { NetworkHealthPage } from './pages/NetworkHealthPage'
import { TopologyPage } from './pages/TopologyPage'
import { ManageAccountsPage } from './pages/ManageAccountsPage'
import { ReportsPage } from './pages/ReportsPage'
import { SystemLogsPage } from './pages/SystemLogsPage'
import { PlaceholderPage } from './pages/PlaceholderPage'

export default function App() {
  return (
    <Routes>

      {/* PUBLIC */}
      <Route path="/login" element={<LoginPage />} />

      {/* PROTECTED / ADMIN */}
      <Route path="/" element={<AdminLayout />}>

        {/* DEFAULT */}
        <Route index element={<Navigate to="/dashboard" replace />} />

        {/* MAIN PAGES */}
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="network-health" element={<NetworkHealthPage />} />
        <Route path="device-inventory" element={<DeviceInventoryPage />} />
        <Route path="reports" element={<ReportsPage />} />
        <Route path="topology" element={<TopologyPage />} />

        {/* ✅ FIXED: REAL PAGE */}
        <Route path="system-logs" element={<SystemLogsPage />} />

        {/* ACCOUNTS */}
        <Route path="accounts" element={<ManageAccountsPage />} />

        {/* PLACEHOLDERS */}
        <Route
          path="plugins"
          element={
            <PlaceholderPage
              title="Plugins"
              description="Manage and configure system plugins."
            />
          }
        />

        <Route
          path="settings"
          element={
            <PlaceholderPage
              title="Settings"
              description="System configuration and preferences."
            />
          }
        />

      </Route>

      {/* FALLBACK */}
      <Route path="*" element={<Navigate to="/login" replace />} />

    </Routes>
  )
}