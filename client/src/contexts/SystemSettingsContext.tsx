// PLEASE WALANG GAGALAW NG KAHIT ANO DITO

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import type { SystemSettings } from '../types/settings'

const CACHE_KEY = 'pinpoint-system-settings-cache'
const SETTINGS_ENDPOINT = '/api/system'
const PREFERENCES_ENDPOINT = '/api/user/preferences'

// Fields that live in UserPreferences (per-user) instead of
// SystemSettings (shared singleton). Keep this in sync with
// UserPreferences.to_dict() on the backend.
const PREFERENCE_KEYS = [
  'theme',
  'timeZone',
  'dateTimeFormat',
  'systemFont',
  'systemFontSize',
  'dashboardLayout',
  'dashboardRefreshRate',
] as const

type PreferenceKey = (typeof PREFERENCE_KEYS)[number]

function pick<T extends object, K extends keyof T>(
  obj: T,
  keys: readonly K[]
): Pick<T, K> {
  const result = {} as Pick<T, K>
  keys.forEach((key) => {
    result[key] = obj[key]
  })
  return result
}

function omit<T extends object, K extends keyof T>(
  obj: T,
  keys: readonly K[]
): Omit<T, K> {
  const result = { ...obj }
  keys.forEach((key) => {
    delete result[key]
  })
  return result
}

export const DEFAULT_SYSTEM_SETTINGS: SystemSettings = {
  theme: 'dark',
  timeZone: 'UTC+08:00',
  dateTimeFormat: 'DD/MM/YYYY',
  systemFont: 'Default',
  systemFontSize: 'medium',
  dashboardRefreshRate: 5,
  scanFrequency: 6,
  dashboardLayout: 'default',
  notifications: true,
  exportFormats: ['CSV', 'PDF', 'XLS'],
  sessionTimeout: 30,
  strongPasswordPolicy: true,
  failedLoginMonitoring: true,
  auditLogging: true,
  securityCheckFrequency: 'weekly',
  systemUpdateFrequency: 'monthly',
  maintenanceMode: false,
  automaticBackups: true,
  logRetentionDays: 30,
  diagnosticHistoryRetentionDays: 90,
  version: 1,
}

interface SystemSettingsContextValue {
  settings: SystemSettings
  savedSettings: SystemSettings
  updateSettings: (updates: Partial<SystemSettings>) => void
  saveSettings: () => Promise<void>
  refreshSettings: () => Promise<void>
  discardChanges: () => void
  resetSettings: () => void
  hasUnsavedChanges: boolean
  isLoading: boolean
  isSaving: boolean
  loadError: string | null
  saveError: string | null
}

const SystemSettingsContext =
  createContext<SystemSettingsContextValue | undefined>(undefined)

/*
|--------------------------------------------------------------------------
| Conflict handling
|
| The backend rejects a save (409) whose `version` is older than the stored
| one, i.e. when settings were saved from somewhere else (another tab,
| another admin) after this page loaded them. Rather than failing outright,
| the provider re-applies only the fields this user actually edited on top
| of the latest settings, and only reports a conflict when someone else
| changed one of those same fields.
|--------------------------------------------------------------------------
*/

class SettingsConflictError extends Error {}

// Bookkeeping fields, not user-editable settings.
const UNTRACKED_KEYS = new Set(['version', 'updatedAt'])

function changedKeys(
  from: SystemSettings,
  to: SystemSettings
): (keyof SystemSettings)[] {
  return (Object.keys(to) as (keyof SystemSettings)[]).filter(
    (key) =>
      !UNTRACKED_KEYS.has(key) &&
      JSON.stringify(from[key]) !== JSON.stringify(to[key])
  )
}

// `latest` with the edits the user made (from `base` to `edited`) applied.
function rebase(
  latest: SystemSettings,
  base: SystemSettings,
  edited: SystemSettings
): SystemSettings {
  const result: SystemSettings = {
    ...latest,
    exportFormats: [...latest.exportFormats],
  }
  for (const key of changedKeys(base, edited)) {
    ;(result as unknown as Record<string, unknown>)[key] = edited[key]
  }
  return result
}

// "sessionTimeout" -> "Session Timeout"
function settingLabel(key: string): string {
  const words = key.replace(/([A-Z])/g, ' $1')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/*
|--------------------------------------------------------------------------
| Local cache helpers (NOT source of truth — instant paint only)
|--------------------------------------------------------------------------
*/

function readCache(): SystemSettings | null {
  try {
    const stored = localStorage.getItem(CACHE_KEY)
    if (!stored) return null

    const parsed = JSON.parse(stored)

    return {
      ...DEFAULT_SYSTEM_SETTINGS,
      ...parsed,
      exportFormats: Array.isArray(parsed.exportFormats)
        ? parsed.exportFormats
        : [...DEFAULT_SYSTEM_SETTINGS.exportFormats],
    }
  } catch {
    return null
  }
}

function writeCache(settings: SystemSettings) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(settings))
  } catch {
    // Non-fatal — cache is a convenience, not a requirement.
  }
}

/*
|--------------------------------------------------------------------------
| Backend calls — two sources merged into one settings object.
| GET/PUT /api/system      -> shared, system-wide fields
| GET/PUT /api/user/preferences -> per-user display preferences
|--------------------------------------------------------------------------
*/

async function fetchSystemSettings(): Promise<Omit<SystemSettings, PreferenceKey>> {
  const res = await fetch(SETTINGS_ENDPOINT, {
    credentials: 'include',
  })

  if (!res.ok) {
    throw new Error(`Failed to load settings (${res.status})`)
  }

  const body = await res.json()
  const data = body.data ?? body

  return {
    ...omit(DEFAULT_SYSTEM_SETTINGS, PREFERENCE_KEYS),
    ...data,
    exportFormats: Array.isArray(data.exportFormats)
      ? data.exportFormats
      : [...DEFAULT_SYSTEM_SETTINGS.exportFormats],
  }
}

async function fetchPreferences(): Promise<Pick<SystemSettings, PreferenceKey>> {
  const res = await fetch(PREFERENCES_ENDPOINT, {
    credentials: 'include',
  })

  if (!res.ok) {
    throw new Error(`Failed to load preferences (${res.status})`)
  }

  const data = await res.json()

  return {
    ...pick(DEFAULT_SYSTEM_SETTINGS, PREFERENCE_KEYS),
    ...data,
  }
}

async function fetchSettings(): Promise<SystemSettings> {
  const [system, preferences] = await Promise.all([
    fetchSystemSettings(),
    fetchPreferences(),
  ])

  return {
    ...system,
    ...preferences,
  } as SystemSettings
}

async function persistSystemSettings(
  settings: SystemSettings
): Promise<Omit<SystemSettings, PreferenceKey>> {
  const res = await fetch(SETTINGS_ENDPOINT, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })

  if (!res.ok) {
    if (res.status === 409) {
      throw new SettingsConflictError(
        'Settings were changed by someone else. Reload and try again.'
      )
    }
    throw new Error(`Failed to save settings (${res.status})`)
  }

  const body = await res.json()
  return body.data ?? body
}

async function persistPreferences(
  settings: SystemSettings
): Promise<Pick<SystemSettings, PreferenceKey>> {
  const res = await fetch(PREFERENCES_ENDPOINT, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(pick(settings, PREFERENCE_KEYS)),
  })

  if (!res.ok) {
    throw new Error(`Failed to save preferences (${res.status})`)
  }

  return res.json()
}

async function persistSettings(
  settings: SystemSettings
): Promise<SystemSettings> {
  const [system, preferences] = await Promise.all([
    persistSystemSettings(settings),
    persistPreferences(settings),
  ])

  return {
    ...system,
    ...preferences,
  } as SystemSettings
}

/*
|--------------------------------------------------------------------------
| Provider
|--------------------------------------------------------------------------
*/

export function SystemSettingsProvider({
  children,
}: {
  children: ReactNode
}) {
  const cached = readCache()

  const [savedSettings, setSavedSettings] = useState<SystemSettings>(
    cached ?? DEFAULT_SYSTEM_SETTINGS
  )

  const [settings, setSettings] = useState<SystemSettings>(
    cached ?? DEFAULT_SYSTEM_SETTINGS
  )

  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const hasUnsavedChanges =
    JSON.stringify(settings) !== JSON.stringify(savedSettings)

  /*
  |--------------------------------------------------------------------------
  | Load from backend on mount — this is the real source of truth.
  | The cached value above only avoids a flash of defaults while this runs.
  |--------------------------------------------------------------------------
  */

  useEffect(() => {
    let cancelled = false

    fetchSettings()
      .then((data) => {
        if (cancelled) return
        setSavedSettings(data)
        setSettings(data)
        writeCache(data)
        setLoadError(null)
      })
      .catch((error) => {
        if (cancelled) return
        console.error('Unable to load system settings:', error)
        setLoadError(
          error instanceof Error ? error.message : 'Unable to load settings'
        )
        // Fall back to whatever we had cached/default — already in state.
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  /*
  |--------------------------------------------------------------------------
  | Keep settings current while the app stays open: reload them whenever the
  | tab regains focus (and when the Settings page opens — see SettingsPage),
  | keeping any unsaved edits on top of the latest values.
  |--------------------------------------------------------------------------
  */

  const stateRef = useRef({ settings, savedSettings, isSaving })
  useEffect(() => {
    stateRef.current = { settings, savedSettings, isSaving }
  })

  const refreshSettings = useCallback(async () => {
    if (stateRef.current.isSaving) return

    try {
      const latest = await fetchSettings()
      const { settings: current, savedSettings: base, isSaving: saving } =
        stateRef.current
      if (saving) return

      setSavedSettings(latest)
      setSettings(rebase(latest, base, current))
      writeCache(latest)
      setLoadError(null)
    } catch (error) {
      // Keep what we have — the next save still detects conflicts.
      console.error('Unable to refresh system settings:', error)
    }
  }, [])

  useEffect(() => {
    const handleVisible = () => {
      if (document.visibilityState === 'visible') {
        void refreshSettings()
      }
    }

    document.addEventListener('visibilitychange', handleVisible)
    window.addEventListener('focus', handleVisible)

    return () => {
      document.removeEventListener('visibilitychange', handleVisible)
      window.removeEventListener('focus', handleVisible)
    }
  }, [refreshSettings])

  function updateSettings(updates: Partial<SystemSettings>) {
    setSettings((current) => ({ ...current, ...updates }))
  }

  // Save onto the latest settings after a version conflict. Throws if
  // someone else changed a field this user also edited, leaving the user's
  // values on screen so a second save deliberately keeps them.
  async function saveOverConflict(): Promise<SystemSettings> {
    const latest = await fetchSettings()
    const edited = changedKeys(savedSettings, settings)
    const conflicts = edited.filter(
      (key) => JSON.stringify(latest[key]) !== JSON.stringify(savedSettings[key])
    )
    const rebased = rebase(latest, savedSettings, settings)

    if (conflicts.length > 0) {
      setSavedSettings(latest)
      setSettings(rebased)
      writeCache(latest)
      throw new Error(
        `${conflicts.map(settingLabel).join(', ')} ${
          conflicts.length === 1 ? 'was' : 'were'
        } also changed by someone else. Your value is still shown — save again to keep it, or discard to use theirs.`
      )
    }

    return persistSettings(rebased)
  }

  async function saveSettings() {
    setIsSaving(true)
    setSaveError(null)

    const toSave: SystemSettings = {
      ...settings,
      exportFormats: [...settings.exportFormats],
    }

    try {
      let confirmed: SystemSettings
      try {
        confirmed = await persistSettings(toSave)
      } catch (error) {
        if (!(error instanceof SettingsConflictError)) throw error
        confirmed = await saveOverConflict()
      }
      setSavedSettings(confirmed)
      setSettings(confirmed)
      writeCache(confirmed)
    } catch (error) {
      console.error('Failed to save system settings:', error)
      setSaveError(
        error instanceof Error ? error.message : 'Failed to save settings'
      )
      throw error
    } finally {
      setIsSaving(false)
    }
  }

  function discardChanges() {
    setSettings({
      ...savedSettings,
      exportFormats: [...savedSettings.exportFormats],
    })
    setSaveError(null)
  }

  function resetSettings() {
    setSettings({
      ...DEFAULT_SYSTEM_SETTINGS,
      exportFormats: [...DEFAULT_SYSTEM_SETTINGS.exportFormats],
      version: savedSettings.version,
    })
  }

  /*
  |--------------------------------------------------------------------------
  | Apply display-only settings to the current DOM/tab.
  | NOTE: this affects only this browser tab's rendering — it is not
  | what makes settings "global". The backend calls above are.
  |
  | Scoped to the lifetime of this provider (mounted only inside the
  | authenticated app shell — see AdminLayout). The cleanup below resets
  | these back to defaults on unmount so unauthenticated routes like
  | /login never inherit a signed-in user's theme/font/layout.
  |
  | Text size is applied as a root font-size percentage rather than a
  | body-level px override: Tailwind's spacing/type scale is rem-based,
  | so scaling the root scales every rem-driven utility in the app
  | proportionally instead of only affecting unstyled text.
  |--------------------------------------------------------------------------
  */

  useEffect(() => {
    const root = document.documentElement

    const rootFontSizes = { small: '87.5%', medium: '100%', large: '112.5%' }
    root.style.fontSize = rootFontSizes[settings.systemFontSize]

    const fonts: Record<string, string> = {
      Default: 'Inter, system-ui, sans-serif',
      Inter: 'Inter, sans-serif',
      Roboto: 'Roboto, sans-serif',
      'Open Sans': '"Open Sans", sans-serif',
    }

    root.style.setProperty(
      '--font-sans',
      fonts[settings.systemFont] ?? fonts.Default
    )

    root.dataset.theme = settings.theme
    root.dataset.dashboardLayout = settings.dashboardLayout
    root.dataset.notifications = String(settings.notifications)
    root.dataset.maintenance = String(settings.maintenanceMode)

    return () => {
      root.style.fontSize = ''
      root.style.removeProperty('--font-sans')
      root.dataset.theme = DEFAULT_SYSTEM_SETTINGS.theme
      root.dataset.dashboardLayout = DEFAULT_SYSTEM_SETTINGS.dashboardLayout
      root.dataset.notifications = String(DEFAULT_SYSTEM_SETTINGS.notifications)
      root.dataset.maintenance = String(DEFAULT_SYSTEM_SETTINGS.maintenanceMode)
    }
  }, [
    settings.theme,
    settings.systemFont,
    settings.systemFontSize,
    settings.dashboardLayout,
    settings.notifications,
    settings.maintenanceMode,
  ])

  return (
    <SystemSettingsContext.Provider
      value={{
        settings,
        savedSettings,
        updateSettings,
        saveSettings,
        refreshSettings,
        discardChanges,
        resetSettings,
        hasUnsavedChanges,
        isLoading,
        isSaving,
        loadError,
        saveError,
      }}
    >
      {children}
    </SystemSettingsContext.Provider>
  )
}

export function useSystemSettings() {
  const context = useContext(SystemSettingsContext)

  if (!context) {
    throw new Error(
      'useSystemSettings must be used inside SystemSettingsProvider'
    )
  }

  return context
}