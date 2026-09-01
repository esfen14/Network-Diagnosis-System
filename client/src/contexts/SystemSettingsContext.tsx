// PLEASE WALANG GAGALAW NG KAHIT ANO DITO

import {
  createContext,
  useContext,
  useEffect,
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
      throw new Error(
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

  function updateSettings(updates: Partial<SystemSettings>) {
    setSettings((current) => ({ ...current, ...updates }))
  }

  async function saveSettings() {
    setIsSaving(true)
    setSaveError(null)

    const toSave: SystemSettings = {
      ...settings,
      exportFormats: [...settings.exportFormats],
    }

    try {
      const confirmed = await persistSettings(toSave)
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