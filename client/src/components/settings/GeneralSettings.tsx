import { SettingsCard } from './SettingsCard'
import { SettingsSelect } from './SettingsSelect'
import { SettingsToggle } from './SettingsToggle'
import { SettingsActions } from './SettingsActions'

import {
  useSystemSettings,
} from '../../contexts/SystemSettingsContext'

const themeOptions = [
  {
    value: 'dark',
    label: 'Dark Theme',
  },
  {
    value: 'light',
    label: 'Light Theme',
  },
]

const timeZoneOptions = [
  {
    value: 'UTC+08:00',
    label: 'UTC+08:00',
  },
  {
    value: 'UTC+00:00',
    label: 'UTC+00:00',
  },
  {
    value: 'UTC-05:00',
    label: 'UTC-05:00',
  },
]

const dateFormatOptions = [
  {
    value: 'DD/MM/YYYY',
    label: 'DD/MM/YYYY',
  },
  {
    value: 'MM/DD/YYYY',
    label: 'MM/DD/YYYY',
  },
  {
    value: 'YYYY-MM-DD',
    label: 'YYYY-MM-DD',
  },
]

const fontOptions = [
  {
    value: 'Default',
    label: 'Default',
  },
  {
    value: 'Inter',
    label: 'Inter',
  },
  {
    value: 'Roboto',
    label: 'Roboto',
  },
  {
    value: 'Open Sans',
    label: 'Open Sans',
  },
]

const fontSizeOptions = [
  {
    value: 'small',
    label: 'Small',
  },
  {
    value: 'medium',
    label: 'Medium',
  },
  {
    value: 'large',
    label: 'Large',
  },
]

const refreshRateOptions = [
  {
    value: '1',
    label: 'Auto Refresh - 1 minute',
  },
  {
    value: '5',
    label: 'Auto Refresh - 5 minutes',
  },
  {
    value: '15',
    label: 'Auto Refresh - 15 minutes',
  },
  {
    value: '0',
    label: 'Manual',
  },
]

const scanFrequencyOptions = [
  {
    value: '1',
    label: 'Every 1 hour',
  },
  {
    value: '3',
    label: 'Every 3 hours',
  },
  {
    value: '6',
    label: 'Every 6 hours',
  },
  {
    value: '12',
    label: 'Every 12 hours',
  },
  {
    value: '24',
    label: 'Daily',
  },
]

const layoutOptions = [
  {
    value: 'default',
    label: 'Default',
  },
  {
    value: 'compact',
    label: 'Compact',
  },
  {
    value: 'expanded',
    label: 'Expanded',
  },
]

const exportOptions = [
  {
    value: 'CSV,PDF,XLS',
    label: 'CSV, PDF & XLS',
  },
  {
    value: 'CSV,PDF',
    label: 'CSV & PDF',
  },
  {
    value: 'CSV,XLS',
    label: 'CSV & XLS',
  },
  {
    value: 'PDF',
    label: 'PDF',
  },
  {
    value: 'CSV',
    label: 'CSV',
  },
]

export function GeneralSettings() {
  const {
    settings,
    updateSettings,
    saveSettings,
    discardChanges,
    resetSettings,
    hasUnsavedChanges,
  } = useSystemSettings()

  return (
    <SettingsCard
      title="General Settings"
      description="Personal display preferences plus shared diagnostic and export behavior."
    >
      <div className="grid gap-x-8 gap-y-7 lg:grid-cols-3">

        {/* COLUMN 1 */}

        <SettingsSelect
          label="Theme"
          value={settings.theme}
          options={themeOptions}
          onChange={(value) =>
            updateSettings({
              theme:
                value as
                  | 'dark'
                  | 'light',
            })
          }
        />

        <SettingsSelect
          label="Time Zone"
          value={settings.timeZone}
          options={timeZoneOptions}
          onChange={(value) =>
            updateSettings({
              timeZone: value,
            })
          }
        />

        <SettingsSelect
          label="System Font"
          value={settings.systemFont}
          options={fontOptions}
          onChange={(value) =>
            updateSettings({
              systemFont: value,
            })
          }
        />

        <SettingsSelect
          label="System Font Size"
          value={
            settings.systemFontSize
          }
          options={fontSizeOptions}
          onChange={(value) =>
            updateSettings({
              systemFontSize:
                value as
                  | 'small'
                  | 'medium'
                  | 'large',
            })
          }
        />

        {/* COLUMN 2 */}

        <SettingsSelect
          label="Date and Time Format"
          value={
            settings.dateTimeFormat
          }
          options={dateFormatOptions}
          onChange={(value) =>
            updateSettings({
              dateTimeFormat: value,
            })
          }
        />

        <SettingsSelect
          label="Dashboard Layout"
          value={
            settings.dashboardLayout
          }
          options={layoutOptions}
          onChange={(value) =>
            updateSettings({
              dashboardLayout:
                value as
                  | 'default'
                  | 'compact'
                  | 'expanded',
            })
          }
        />

        <SettingsToggle
          label="Notifications"
          description="Enable system-wide notifications"
          enabled={
            settings.notifications
          }
          onChange={(enabled) =>
            updateSettings({
              notifications: enabled,
            })
          }
        />

        <SettingsSelect
          label="Dashboard Refresh Rate"
          value={String(
            settings.dashboardRefreshRate
          )}
          options={refreshRateOptions}
          onChange={(value) =>
            updateSettings({
              dashboardRefreshRate:
                Number(value),
            })
          }
        />

        <SettingsSelect
          label="Export Formats"
          value={
            settings.exportFormats.join(',')
          }
          options={exportOptions}
          onChange={(value) =>
            updateSettings({
              exportFormats:
                value.split(','),
            })
          }
        />

        {/* COLUMN 3 */}

        <SettingsSelect
          label="Scan Frequency"
          value={String(
            settings.scanFrequency
          )}
          options={scanFrequencyOptions}
          onChange={(value) =>
            updateSettings({
              scanFrequency:
                Number(value),
            })
          }
        />

        <div className="rounded-2xl bg-[var(--card-alt)] border border-[var(--border)] p-4 lg:col-span-1">
          <p className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Current Scan Schedule</p>
          <p className="mt-2 text-sm font-medium text-[var(--text)]">{getScanDescription(settings.scanFrequency)}</p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">This setting will control automated diagnostic scans once connected to the backend.</p>
        </div>

        <div className="rounded-2xl bg-[var(--card-alt)] border border-[var(--border)] p-4 lg:col-span-1">
          <p className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Setting Scope</p>
          <p className="mt-2 text-sm font-medium text-[var(--text)]">Mixed</p>
          <p className="mt-1 text-xs text-[var(--text-muted)]">Display preferences (theme, fonts, layout, refresh rate) apply only to your account. Scan frequency, notifications, and export formats are shared system-wide.</p>
        </div>

      </div>

      <SettingsActions
        hasChanges={hasUnsavedChanges}
        onSave={saveSettings}
        onDiscard={discardChanges}
        onReset={resetSettings}
      />
    </SettingsCard>
  )
}

function getScanDescription(
  frequency: number
) {
  if (frequency === 1) {
    return 'Every 1 hour'
  }

  if (frequency === 24) {
    return 'Once per day'
  }

  return `Every ${frequency} hours`
}