import { act, render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  DEFAULT_SYSTEM_SETTINGS,
  SystemSettingsProvider,
  useSystemSettings,
} from '../contexts/SystemSettingsContext'

// A tiny fake backend for /api/system (versioned) and /api/user/preferences.
const PREFERENCE_KEYS = [
  'theme', 'timeZone', 'dateTimeFormat', 'systemFont',
  'systemFontSize', 'dashboardLayout', 'dashboardRefreshRate',
]

let server: Record<string, unknown>
let systemPuts: Record<string, unknown>[]

function splitSystem(all: Record<string, unknown>) {
  const system: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(all)) {
    if (!PREFERENCE_KEYS.includes(key)) system[key] = value
  }
  return system
}

function respond(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

const fetchMock = vi.fn((url: string, init?: RequestInit) => {
  const method = init?.method ?? 'GET'
  const body = init?.body ? JSON.parse(String(init.body)) : undefined

  if (url === '/api/system' && method === 'GET') {
    return respond(200, { success: true, data: splitSystem(server) })
  }
  if (url === '/api/system' && method === 'PUT') {
    systemPuts.push(body)
    if (body.version !== server.version) {
      return respond(409, { success: false, message: 'conflict' })
    }
    server = { ...server, ...splitSystem(body), version: (server.version as number) + 1 }
    return respond(200, { success: true, data: splitSystem(server) })
  }
  if (url === '/api/user/preferences') {
    return respond(200, Object.fromEntries(PREFERENCE_KEYS.map((key) => [key, server[key]])))
  }
  return respond(404, {})
})

// Someone else saving from another tab/admin.
function changeOnServer(updates: Record<string, unknown>) {
  server = { ...server, ...updates, version: (server.version as number) + 1 }
}

let api: ReturnType<typeof useSystemSettings>

function Probe() {
  api = useSystemSettings()
  return (
    <div>
      <span data-testid="timeout">{api.settings.sessionTimeout}</span>
      <span data-testid="scan">{api.settings.scanFrequency}</span>
      <span data-testid="error">{api.saveError ?? ''}</span>
    </div>
  )
}

async function renderLoaded() {
  render(
    <SystemSettingsProvider>
      <Probe />
    </SystemSettingsProvider>,
  )
  await waitFor(() => expect(api.isLoading).toBe(false))
}

async function save() {
  await act(async () => {
    await api.saveSettings().catch(() => {})
  })
}

describe('SystemSettingsProvider conflict handling', () => {
  beforeEach(() => {
    localStorage.clear()
    server = { ...DEFAULT_SYSTEM_SETTINGS, version: 1 }
    systemPuts = []
    fetchMock.mockClear()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('saves normally when nothing changed elsewhere', async () => {
    await renderLoaded()

    act(() => api.updateSettings({ sessionTimeout: 60 }))
    await save()

    expect(systemPuts).toHaveLength(1)
    expect(server.sessionTimeout).toBe(60)
    expect(screen.getByTestId('error')).toHaveTextContent('')
  })

  it('keeps both changes when someone else edited a different field', async () => {
    await renderLoaded()
    changeOnServer({ scanFrequency: 12 })

    act(() => api.updateSettings({ sessionTimeout: 60 }))
    await save()

    expect(systemPuts).toHaveLength(2)
    expect(server.sessionTimeout).toBe(60)
    expect(server.scanFrequency).toBe(12)
    expect(screen.getByTestId('scan')).toHaveTextContent('12')
    expect(screen.getByTestId('error')).toHaveTextContent('')
  })

  it('reports a conflict on the same field, then keeps the user value on a second save', async () => {
    await renderLoaded()
    changeOnServer({ sessionTimeout: 15 })

    act(() => api.updateSettings({ sessionTimeout: 60 }))
    await save()

    expect(server.sessionTimeout).toBe(15)
    expect(screen.getByTestId('error')).toHaveTextContent(
      'Session Timeout was also changed by someone else',
    )
    expect(screen.getByTestId('timeout')).toHaveTextContent('60')

    await save()

    expect(server.sessionTimeout).toBe(60)
    expect(screen.getByTestId('error')).toHaveTextContent('')
  })

  it('refreshes on focus and keeps unsaved edits', async () => {
    await renderLoaded()
    act(() => api.updateSettings({ sessionTimeout: 60 }))
    changeOnServer({ scanFrequency: 3 })

    await act(async () => {
      window.dispatchEvent(new Event('focus'))
    })

    await waitFor(() => expect(screen.getByTestId('scan')).toHaveTextContent('3'))
    expect(screen.getByTestId('timeout')).toHaveTextContent('60')
    expect(api.savedSettings.version).toBe(2)

    await save()

    expect(systemPuts).toHaveLength(1)
    expect(server.sessionTimeout).toBe(60)
    expect(server.scanFrequency).toBe(3)
  })
})
