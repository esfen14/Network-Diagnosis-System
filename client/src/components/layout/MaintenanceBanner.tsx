import { Wrench } from 'lucide-react'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'

// Shown on every page while Settings → System → Maintenance Mode is on.
// Scheduled scans, update checks and security checks are paused on the
// back end for as long as it stays on (see server/app/automation.py).
export function MaintenanceBanner() {
  const { savedSettings } = useSystemSettings()

  if (!savedSettings.maintenanceMode) return null

  return (
    <div
      role="status"
      className="mb-4 ml-55 flex items-center gap-3 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-400/30 dark:bg-amber-400/10 dark:text-amber-200"
    >
      <Wrench className="h-4 w-4 shrink-0" />
      <span>
        <strong className="font-semibold">Maintenance mode is on.</strong>{' '}
        Scheduled scans, update checks and security checks are paused until it is turned off.
      </span>
    </div>
  )
}
