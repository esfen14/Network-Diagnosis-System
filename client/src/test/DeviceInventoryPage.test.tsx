import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { DeviceInventoryPage } from '../pages/DeviceInventoryPage'

vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ settings: { theme: 'dark' } }),
}))

const apiGet = vi.fn()
const apiPost = vi.fn()
const apiDelete = vi.fn()

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<typeof import('../lib/api')>('../lib/api')
  return {
    ...actual,
    apiGet: (path: string) => apiGet(path),
    apiPost: (path: string, data?: unknown) => apiPost(path, data),
    apiDelete: (path: string, data?: unknown) => apiDelete(path, data),
  }
})

// ─── API fixtures (server/app/api/system/network_hosts.py shapes) ───────────

function host(hostname: string, state: string, ack: { comment: string; acknowledged_by: string; acknowledged_at: string } | null = null) {
  return {
    hostname,
    state,
    state_type: 'HARD',
    last_check: '2026-09-26T10:00:00+00:00',
    check_latency: 0.012,
    plugin_output: `PING ${state}`,
    is_flapping: false,
    in_downtime: false,
    nagios_ack: 'none',
    ack,
  }
}

const HOSTS = [
  host('gateway', 'Up'),
  host('switch-1', 'Down'),
  host('printer', 'Unreachable', {
    comment: 'Replacing toner',
    acknowledged_by: 'Admin User',
    acknowledged_at: '2026-09-26T09:00:00+00:00',
  }),
]

function listResponse(items: unknown[], overrides: Record<string, unknown> = {}) {
  return { items, page: 1, per_page: 10, pages: 1, total: items.length, has_next: false, has_prev: false, ...overrides }
}

let tableResponse: unknown

function routeApi(path: string) {
  const params = new URLSearchParams(path.split('?')[1])
  // Summary-card counts use per_page=1; the table uses per_page=10.
  if (params.get('per_page') === '1') {
    return Promise.resolve(listResponse([], { total: params.get('state') === 'UP' ? 2 : 3 }))
  }
  return tableResponse instanceof Error ? Promise.reject(tableResponse) : Promise.resolve(tableResponse)
}

function tableCalls() {
  return apiGet.mock.calls
    .map(([path]) => new URLSearchParams(path.split('?')[1]))
    .filter((params) => params.get('per_page') === '10')
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DeviceInventoryPage />
    </MemoryRouter>,
  )
}

async function renderLoaded() {
  renderPage()
  await waitFor(() => expect(screen.queryByText('Loading hosts…')).not.toBeInTheDocument())
}

function statCard(title: string) {
  return screen.getByText(title).closest('.rounded-3xl') as HTMLElement
}

function row(hostname: string) {
  return screen.getByText(hostname).closest('tr') as HTMLElement
}

describe('DeviceInventoryPage', () => {
  beforeEach(() => {
    tableResponse = listResponse(HOSTS)
    apiGet.mockReset()
    apiPost.mockReset()
    apiDelete.mockReset()
    apiGet.mockImplementation(routeApi)
    apiPost.mockResolvedValue({})
    apiDelete.mockResolvedValue({})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows the Host Inventory heading', async () => {
    await renderLoaded()
    expect(screen.getByText('Host Inventory')).toBeInTheDocument()
    expect(screen.getAllByText('All Hosts').length).toBeGreaterThan(0)
  })

  it('fills the summary cards from the host counts', async () => {
    await renderLoaded()
    await waitFor(() => expect(within(statCard('Total Hosts')).getByText('3')).toBeInTheDocument())
    expect(within(statCard('Up')).getByText('2')).toBeInTheDocument()
    expect(within(statCard('Down / Unreachable')).getByText('1')).toBeInTheDocument()
  })

  it('lists every host with its latency', async () => {
    await renderLoaded()
    for (const name of ['gateway', 'switch-1', 'printer']) {
      expect(screen.getByText(name)).toBeInTheDocument()
    }
    expect(within(row('gateway')).getByText('0.012s')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 1 · 3 hosts total')).toBeInTheDocument()
  })

  it('requests the first page sorted by hostname', async () => {
    await renderLoaded()
    const params = tableCalls()[0]
    expect(params.get('page')).toBe('1')
    expect(params.get('sort_by')).toBe('hostname')
    expect(params.get('order')).toBe('asc')
    expect(params.has('state')).toBe(false)
  })

  it('offers Acknowledge only for unacknowledged hosts that are not up', async () => {
    await renderLoaded()
    expect(within(row('gateway')).queryByRole('button')).not.toBeInTheDocument()
    expect(within(row('switch-1')).getByRole('button', { name: 'Acknowledge' })).toBeInTheDocument()
    expect(within(row('printer')).getByRole('button', { name: 'Unacknowledge' })).toBeInTheDocument()
    expect(within(row('printer')).getByText('By Admin User')).toBeInTheDocument()
  })

  it('shows an empty state when no hosts match', async () => {
    tableResponse = listResponse([])
    await renderLoaded()
    expect(screen.getByText('No hosts match your search or filter')).toBeInTheDocument()
  })

  it('filters by state', async () => {
    const user = userEvent.setup()
    await renderLoaded()

    await user.click(screen.getByRole('button', { name: 'Filter' }))
    await user.click(screen.getByRole('button', { name: 'DOWN' }))

    await waitFor(() => expect(tableCalls().at(-1)?.get('state')).toBe('DOWN'))
  })

  it('searches by hostname after typing', async () => {
    const user = userEvent.setup()
    await renderLoaded()

    await user.type(screen.getByPlaceholderText('Search hostname'), 'switch')

    await waitFor(() => expect(tableCalls().at(-1)?.get('search')).toBe('switch'))
  })

  it('toggles the sort order', async () => {
    const user = userEvent.setup()
    await renderLoaded()

    await user.click(screen.getByRole('button', { name: 'Sort' }))

    await waitFor(() => expect(tableCalls().at(-1)?.get('order')).toBe('desc'))
  })

  it('moves to the next page', async () => {
    tableResponse = listResponse(HOSTS, { pages: 2, total: 13, has_next: true })
    const user = userEvent.setup()
    await renderLoaded()

    await user.click(screen.getByRole('button', { name: 'Next' }))

    await waitFor(() => expect(tableCalls().at(-1)?.get('page')).toBe('2'))
  })

  it('acknowledges a host with a comment', async () => {
    const user = userEvent.setup()
    await renderLoaded()

    await user.click(within(row('switch-1')).getByRole('button', { name: 'Acknowledge' }))
    await user.type(screen.getByPlaceholderText(/investigating/i), 'Cable unplugged')
    const dialog = screen.getByText('Acknowledge switch-1').closest('div') as HTMLElement
    await user.click(within(dialog).getByRole('button', { name: 'Acknowledge' }))

    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/system/network-health/hosts/acknowledge', {
        hostname: 'switch-1',
        comment: 'Cable unplugged',
      })
    })
  })

  it('removes an acknowledgement', async () => {
    const user = userEvent.setup()
    await renderLoaded()

    await user.click(within(row('printer')).getByRole('button', { name: 'Unacknowledge' }))

    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith('/api/system/network-health/hosts/acknowledge', { hostname: 'printer' })
    })
  })

  it('shows an error banner when loading fails', async () => {
    tableResponse = new Error('Unable to reach server')
    renderPage()
    expect(await screen.findByText('Unable to reach server')).toBeInTheDocument()
  })
})
