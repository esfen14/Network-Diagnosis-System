import { SettingsCard } from './SettingsCard'
import { SettingsSelect } from './SettingsSelect'
import { SettingsToggle } from './SettingsToggle'
import { SettingsActions } from './SettingsActions'

import {
  useSystemSettings,
} from '../../contexts/SystemSettingsContext'

const sessionTimeoutOptions = [
  {
    value: '15',
    label: '15 minutes',
  },
  {
    value: '30',
    label: '30 minutes',
  },
  {
    value: '60',
    label: '1 hour',
  },
  {
    value: '120',
    label: '2 hours',
  },
  {
    value: '240',
    label: '4 hours',
  },
]

const securityFrequencyOptions = [
  {
    value: 'daily',
    label: 'Daily',
  },
  {
    value: 'weekly',
    label: 'Weekly',
  },
  {
    value: 'monthly',
    label: 'Monthly',
  },
]

export function SecuritySettings() {
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
        title="Authentication & Access"
        description="Configure security behavior for the entire system."
      >
        <div className="grid gap-x-8 gap-y-7 lg:grid-cols-3">

          <SettingsSelect
            label="Session Timeout"
            value={String(
              settings.sessionTimeout
            )}
            options={
              sessionTimeoutOptions
            }
            onChange={(value) =>
              updateSettings({
                sessionTimeout:
                  Number(value),
              })
            }
          />

          <SettingsSelect
            label="Security Check Frequency"
            value={
              settings.securityCheckFrequency
            }
            options={
              securityFrequencyOptions
            }
            onChange={(value) =>
              updateSettings({
                securityCheckFrequency:
                  value as
                    | 'daily'
                    | 'weekly'
                    | 'monthly',
              })
            }
          />

          <SettingsToggle
            label="Strong Password Policy"
            description="Require stronger passwords for accounts"
            enabled={
              settings.strongPasswordPolicy
            }
            onChange={(enabled) =>
              updateSettings({
                strongPasswordPolicy:
                  enabled,
              })
            }
          />

          <SettingsToggle
            label="Failed Login Monitoring"
            description="Monitor repeated failed login attempts"
            enabled={
              settings.failedLoginMonitoring
            }
            onChange={(enabled) =>
              updateSettings({
                failedLoginMonitoring:
                  enabled,
              })
            }
          />

          <SettingsToggle
            label="Audit Logging"
            description="Record important system actions"
            enabled={
              settings.auditLogging
            }
            onChange={(enabled) =>
              updateSettings({
                auditLogging: enabled,
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
        title="Security Information"
        description="Current security configuration."
      >
        <div className="grid gap-4 md:grid-cols-3">

          <SecurityStatus
            title="Password Policy"
            enabled={
              settings.strongPasswordPolicy
            }
          />

          <SecurityStatus
            title="Login Monitoring"
            enabled={
              settings.failedLoginMonitoring
            }
          />

          <SecurityStatus
            title="Audit Logging"
            enabled={
              settings.auditLogging
            }
          />

        </div>
      </SettingsCard>

    </div>
  )
}

function SecurityStatus({
  title,
  enabled,
}: {
  title: string
  enabled: boolean
}) {
  return (
    <div className="rounded-2xl bg-[#20252c] p-5">
      <p className="text-sm font-medium text-white">
        {title}
      </p>

      <div className="mt-3 flex items-center gap-2">
        <span
          className={`
            h-2.5
            w-2.5
            rounded-full
            ${
              enabled
                ? 'bg-pinpoint-green-bright'
                : 'bg-gray-500'
            }
          `}
        />

        <span
          className={`
            text-sm
            ${
              enabled
                ? 'text-pinpoint-green'
                : 'text-gray-500'
            }
          `}
        >
          {enabled
            ? 'Enabled'
            : 'Disabled'}
        </span>
      </div>
    </div>
  )
}