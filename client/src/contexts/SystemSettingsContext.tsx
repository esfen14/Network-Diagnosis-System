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
const SETTINGS_ENDPOINT = '/api/settings'

export const DEFAULT_SYSTEM_SETTINGS: SystemSettings = {
  systemLanguage: 'English',
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
| Backend calls
|--------------------------------------------------------------------------
*/

async function fetchSettings(): Promise<SystemSettings> {
  const res = await fetch(SETTINGS_ENDPOINT, {
    credentials: 'include',
  })

  if (!res.ok) {
    throw new Error(`Failed to load settings (${res.status})`)
  }

  const data = await res.json()

  return {
    ...DEFAULT_SYSTEM_SETTINGS,
    ...data,
    exportFormats: Array.isArray(data.exportFormats)
      ? data.exportFormats
      : [...DEFAULT_SYSTEM_SETTINGS.exportFormats],
  }
}

async function persistSettings(
  settings: SystemSettings
): Promise<SystemSettings> {
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

  return res.json()
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
  |--------------------------------------------------------------------------
  */

  useEffect(() => {
    const root = document.documentElement

    root.setAttribute('lang', settings.systemLanguage === 'Filipino' ? 'fil' : 'en')

    const fontSizes = { small: '14px', medium: '15px', large: '17px' }
    document.body.style.fontSize = fontSizes[settings.systemFontSize]

    const fonts: Record<string, string> = {
      Default: 'Inter, system-ui, sans-serif',
      Inter: 'Inter, sans-serif',
      Roboto: 'Roboto, sans-serif',
      'Open Sans': '"Open Sans", sans-serif',
    }

    // Set the --font-sans CSS variable on <html> rather than an inline
    // style on <body>. Tailwind's own base reset applies font-family to
    // <html> via var(--default-font-family) -> var(--font-sans), so
    // setting an inline style on <body> alone left descendant elements
    // (h1, p, etc.) still inheriting Inter from <html> instead of the
    // chosen font. Updating the variable at the source fixes it for
    // every element that inherits normally, with no per-element overrides.
    root.style.setProperty(
      '--font-sans',
      fonts[settings.systemFont] ?? fonts.Default
    )

    root.dataset.theme = settings.theme
    root.dataset.language = settings.systemLanguage
    root.dataset.dashboardLayout = settings.dashboardLayout
    root.dataset.notifications = String(settings.notifications)
    root.dataset.maintenance = String(settings.maintenanceMode)
  }, [
    settings.systemLanguage,
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