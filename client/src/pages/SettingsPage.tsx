import {
  Cog,
  Lock,
  ServerCog,
} from 'lucide-react'

import { useState } from 'react'

import { GeneralSettings } from '../components/settings/GeneralSettings'
import { SecuritySettings } from '../components/settings/SecuritySettings'
import { SystemSettings } from '../components/settings/SystemSettings'

type SettingsTab =
  | 'general'
  | 'security'
  | 'system'

export function SettingsPage() {
  const [activeTab, setActiveTab] =
    useState<SettingsTab>('general')

    console.log('Settings active tab:', activeTab)

  const tabs = [
    {
      id: 'general' as const,
      label: 'General Settings',
      icon: Cog,
    },
    {
      id: 'security' as const,
      label: 'Security',
      icon: Lock,
    },
    {
      id: 'system' as const,
      label: 'System',
      icon: ServerCog,
    },
  ]

  return (
    <main className="ml-[220px] flex-1">
      <div className="min-h-screen p-6">

        {/* HEADER */}

        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-white">
            System Settings
          </h1>

          <p className="mt-1 text-sm text-gray-400">
            Setup and edit system settings and preferences
          </p>
        </div>

        {/* TABS */}

        <div className="border-b border-gray-600">
          <div className="flex gap-8">

            {tabs.map((tab) => {
              const Icon = tab.icon

              const active =
                activeTab === tab.id

              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() =>
                    setActiveTab(tab.id)
                  }
                  className={`
                    flex
                    items-center
                    gap-2
                    border-b-2
                    px-1
                    pb-3
                    text-sm
                    font-medium
                    transition
                    ${
                      active
                        ? `
                          border-pinpoint-orange
                          text-pinpoint-orange
                        `
                        : `
                          border-transparent
                          text-gray-400
                          hover:text-white
                        `
                    }
                  `}
                >
                  <Icon size={15} />

                  {tab.label}
                </button>
              )
            })}

          </div>
        </div>


        <div className="mt-10">

          {activeTab === 'general' && (
            <GeneralSettings />
          )}

          {activeTab === 'security' && (
            <SecuritySettings />
          )}

          {activeTab === 'system' && (
            <SystemSettings />
          )}

        </div>

      </div>
    </main>
  )
}