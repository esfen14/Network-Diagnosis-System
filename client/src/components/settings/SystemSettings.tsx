import {
  Database,
  HardDrive,
  History,
  Wrench,
} from 'lucide-react'

import { SettingsCard } from './SettingsCard'
import { SettingsSelect } from './SettingsSelect'
import { SettingsToggle } from './SettingsToggle'
import { SettingsActions } from './SettingsActions'

import {
  useSystemSettings,
} from '../../contexts/SystemSettingsContext'

const updateFrequencyOptions = [
  {
    value: 'weekly',
    label: 'Weekly',
  },
  {
    value: 'monthly',
    label: 'Monthly',
  },
  {
    value: 'quarterly',
    label: 'Quarterly',
  },
  {
    value: 'manual',
    label: 'Manual',
  },
]

const retentionOptions = [
  {
    value: '7',
    label: '7 days',
  },
  {
    value: '30',
    label: '30 days',
  },
  {
    value: '60',
    label: '60 days',
  },
  {
    value: '90',
    label: '90 days',
  },
  {
    value: '180',
    label: '180 days',
  },
  {
    value: '365',
    label: '1 year',
  },
]

export function SystemSettings() {
  const {
    settings,
    updateSettings,
    saveSettings,
    discardChanges,
    hasUnsavedChanges,
  } = useSystemSettings()

  return (
    <div className="space-y-6">

      <SettingsCard
        title="System Configuration"
        description="Manage system-wide maintenance, updates, and storage behavior."
      >
        <div className="grid gap-x-8 gap-y-7 lg:grid-cols-3">

          <SettingsSelect
            label="System Update Frequency"
            value={
              settings.systemUpdateFrequency
            }
            options={
              updateFrequencyOptions
            }
            onChange={(value) =>
              updateSettings({
                systemUpdateFrequency:
                  value as
                    | 'weekly'
                    | 'monthly'
                    | 'quarterly'
                    | 'manual',
              })
            }
          />

          <SettingsToggle
            label="Maintenance Mode"
            description="Temporarily place the system into maintenance mode"
            enabled={
              settings.maintenanceMode
            }
            onChange={(enabled) =>
              updateSettings({
                maintenanceMode:
                  enabled,
              })
            }
          />

          <SettingsToggle
            label="Automatic Backups"
            description="Enable automatic system/database backups"
            enabled={
              settings.automaticBackups
            }
            onChange={(enabled) =>
              updateSettings({
                automaticBackups:
                  enabled,
              })
            }
          />

          <SettingsSelect
            label="System Log Retention"
            value={String(
              settings.logRetentionDays
            )}
            options={retentionOptions}
            onChange={(value) =>
              updateSettings({
                logRetentionDays:
                  Number(value),
              })
            }
          />

          <SettingsSelect
            label="Diagnostic History Retention"
            value={String(
              settings.diagnosticHistoryRetentionDays
            )}
            options={retentionOptions}
            onChange={(value) =>
              updateSettings({
                diagnosticHistoryRetentionDays:
                  Number(value),
              })
            }
          />

        </div>

        <SettingsActions
          hasChanges={hasUnsavedChanges}
       
          onSave={saveSettings}
          onDiscard={discardChanges}
        />
        
      </SettingsCard>

      <SettingsCard
        title="System Status"
        description="Overview of configuration states."
      >
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">

          <StatusCard
            icon={Wrench}
            title="Maintenance"
            status={
              settings.maintenanceMode
                ? 'Active'
                : 'Normal'
            }
            active={
              settings.maintenanceMode
            }
          />

          <StatusCard
            icon={Database}
            title="Automatic Backups"
            status={
              settings.automaticBackups
                ? 'Enabled'
                : 'Disabled'
            }
            active={
              settings.automaticBackups
            }
          />

          <StatusCard
            icon={HardDrive}
            title="Log Retention"
            status={`${settings.logRetentionDays} days`}
            active
          />

          <StatusCard
            icon={History}
            title="Diagnostic History"
            status={`${settings.diagnosticHistoryRetentionDays} days`}
            active
          />

        </div>
      </SettingsCard>

    </div>
  )
}

function StatusCard({
  icon: Icon,
  title,
  status,
  active,
}: {
  icon: typeof Wrench
  title: string
  status: string
  active: boolean
}) {
  return (
    <div className="rounded-2xl bg-[#20252c] p-5">

      <Icon
        size={20}
        className="text-pinpoint-orange"
      />

      <p className="mt-4 text-sm font-medium text-white">
        {title}
      </p>

      <div className="mt-2 flex items-center gap-2">

        <span
          className={`
            h-2
            w-2
            rounded-full
            ${
              active
                ? 'bg-pinpoint-green-bright'
                : 'bg-gray-500'
            }
          `}
        />

        <span
          className="text-xs text-gray-400"
        >
          {status}
        </span>

      </div>
    </div>
  )
}