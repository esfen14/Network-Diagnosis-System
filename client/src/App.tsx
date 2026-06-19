import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminLayout } from './components/layout/AdminLayout'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { DeviceInventoryPage } from './pages/DeviceInventoryPage'
import { NetworkHealthPage } from './pages/NetworkHealthPage'
import { ManageAccountsPage } from './pages/ManageAccountsPage'
import { PlaceholderPage } from './pages/PlaceholderPage'

export default function App() {
  return (
    <Routes>
      {/* PUBLIC ROUTES */}
      <Route path="/login" element={<LoginPage />} />

      {/* ADMIN LAYOUT ROUTES */}
      <Route path="/" element={<AdminLayout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />

        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="network-health" element={<NetworkHealthPage />} />
        <Route path="device-inventory" element={<DeviceInventoryPage />} />

        {/* TOPOLOGY */}
        <Route
          path="topology"
          element={
            <PlaceholderPage
              title="Topology View"
              description="Visual map of your network infrastructure."
            />
          }
        />

        {/* REPORTS */}
        <Route
          path="reports"
          element={
            <PlaceholderPage
              title="Reports"
              description="Device and link health reports."
            />
          }
        />

        {/* SYSTEM LOGS */}
        <Route
          path="system-logs"
          element={
            <PlaceholderPage
              title="System Logs"
              description="View system activity and audit logs."
            />
          }
        />

        {/* ✅ FIXED: ACCOUNTS PAGE */}
        <Route path="accounts" element={<ManageAccountsPage />} />

        {/* SETTINGS */}
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