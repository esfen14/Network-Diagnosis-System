import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminLayout } from './components/layout/AdminLayout'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { DeviceInventoryPage } from './pages/DeviceInventoryPage'
import { NetworkHealthPage } from './pages/NetworkHealthPage'
import { TopologyPage } from './pages/TopologyPage'
import { ManageAccountsPage } from './pages/ManageAccountsPage'
import { PlaceholderPage } from './pages/PlaceholderPage'

export default function App() {
  return (
    <Routes>
      
      <Route path="/login" element={<LoginPage />} />
   
      <Route path="/" element={<AdminLayout />}>
        <Route index element={<Navigate to="/login" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="network-health" element={<NetworkHealthPage />} />
        <Route path="device-inventory" element={<DeviceInventoryPage />} />
     
        <Route
          path="topology"
          element={<TopologyPage />}
        />
     
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
       
        <Route path="accounts" element={<ManageAccountsPage />} />
     
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
  
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}