import { Cog, Lock, ServerCog } from 'lucide-react'
import { useEffect, useState } from 'react'

import { GeneralSettings } from '../components/settings/GeneralSettings'
import { SecuritySettings } from '../components/settings/SecuritySettings'
import { SystemSettings } from '../components/settings/SystemSettings'
import { useSystemSettings } from '../contexts/SystemSettingsContext'
import { useCurrentUser } from '../contexts/CurrentUserContext'
import { SETTINGS_TAB_PERMISSIONS } from '../lib/pageAccess'

type SettingsTab = 'general' | 'security' | 'system'

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('general')
  const { refreshSettings } = useSystemSettings()
  const { hasPermission } = useCurrentUser()

  // The app shell loads settings once at login; fetch the latest on
  // opening this page so edits start from what is actually saved.
  useEffect(() => {
    void refreshSettings()
  }, [refreshSettings])

  // General is for everyone; Security and System need their permission
  // (assigned per role in Manage Roles).
  const tabs = [
    { id: 'general' as const, label: 'General Settings', icon: Cog },
    { id: 'security' as const, label: 'Security', icon: Lock },
    { id: 'system' as const, label: 'System', icon: ServerCog },
  ].filter((tab) => tab.id === 'general' || hasPermission(SETTINGS_TAB_PERMISSIONS[tab.id]))

  // Fall back to General if the open tab's permission was removed.
  const shownTab = tabs.some((tab) => tab.id === activeTab) ? activeTab : 'general'

  return (
    <main className="ml-55 flex-1">
      <div className="min-h-screen p-6">

        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-[var(--text)]">System Settings</h1>
          <p className="mt-1 text-sm text-[var(--text-muted)]">Setup and edit system settings and preferences</p>
        </div>

        <div className="border-b border-[var(--border)]">
          <div className="flex gap-8">
            {tabs.map((tab) => {
              const Icon = tab.icon
              const active = shownTab === tab.id
              return (
                <button key={tab.id} type="button" onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 border-b-2 px-1 pb-3 text-sm font-medium transition ${
                    active ? 'border-[#ffb100] text-[var(--text)]' : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text)]'
                  }`}
                >
                  <Icon size={15} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>

        <div className="mt-10">
          {shownTab === 'general' && <GeneralSettings />}
          {shownTab === 'security' && <SecuritySettings />}
          {shownTab === 'system' && <SystemSettings />}
        </div>

      </div>
    </main>
  )
}
