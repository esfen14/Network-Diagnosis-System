import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { NcpaDeploymentPage } from '../pages/NcpaDeploymentPage'
import type { DeploymentRun, NcpaDevice, RunCounts } from '../types/ncpaDeployment'

const api = vi.hoisted(() => ({
  getNcpaDevices: vi.fn(),
  getRuns: vi.fn(),
  getRun: vi.fn(),
  reviewRun: vi.fn(),
  getLatestRun: vi.fn(),
  stopDeployment: vi.fn(),
  getLiveFingerprint: vi.fn(),
  confirmTrust: vi.fn(),
  checkCredentials: vi.fn(),
  startDeployment: vi.fn(),
}))

vi.mock('../lib/ncpaDeploymentApi', () => ({
  ...api,
  NCPA_DEPLOYMENT_STARTED_EVENT: 'nds:ncpa-deployment-started',
}))

vi.mock('../contexts/SystemSettingsContext', () => ({
  useSystemSettings: () => ({ settings: { dateTimeFormat: 'DD/MM/YYYY', timeZone: 'UTC+00:00' } }),
}))

function device(id: number, hostname: string, overrides: Partial<NcpaDevice> = {}): NcpaDevice {
  return {
    id,
    hostname,
    ipAddress: `10.0.20.${id}`,
    trusted: true,
    fingerprint: `KEY${id}`,
    agentStatus: 'Pending NCPA',
    lastError: null,
    lastOutcome: null,
    lastRunId: null,
    deployable: true,
    ...overrides,
  }
}

const DEVICES = [
  device(1, 'web-01', { agentStatus: 'Deployed NCPA', deployable: false, lastOutcome: 'Success' }),
  device(2, 'db-02', { trusted: false, fingerprint: null }),
  device(3, 'app-03', { agentStatus: 'Deployment Failed', lastOutcome: 'Failed', lastError: 'SSH authentication failed.' }),
  device(6, 'nas-06', { agentStatus: 'Deployment Failed', lastOutcome: 'Down', lastError: 'Device unreachable.' }),
]

function counts(overrides: Partial<RunCounts> = {}): RunCounts {
  return { pending: 0, running: 0, success: 0, failed: 0, down: 0, incompatible: 0, rejected: 0, skipped: 0, ...overrides }
}

function run(overrides: Partial<DeploymentRun> = {}): DeploymentRun {
  return {
    id: 11,
    status: 'Partial Failure',
    progress: 100,
    message: 'Deployed NCPA to 1 device(s); 2 failed.',
    error: null,
    startAt: new Date('2026-10-03T16:40:00Z'),
    completedAt: new Date('2026-10-03T16:44:05Z'),
    startedBy: 'Admin User',
    counts: counts({ success: 1, failed: 1, down: 1 }),
    reviewedAt: null,
    reviewedBy: null,
    needsReview: true,
    devices: [
      { deviceId: 1, hostname: 'web-01', ipAddress: '10.0.20.1', outcome: 'Success', error: null },
      { deviceId: 3, hostname: 'app-03', ipAddress: '10.0.20.3', outcome: 'Failed', error: 'SSH authentication failed.' },
      { deviceId: 6, hostname: 'nas-06', ipAddress: '10.0.20.6', outcome: 'Down', error: 'Device unreachable.' },
    ],
    ...overrides,
  }
}

function renderPage(path = '/ncpa-deployment') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/ncpa-deployment" element={<NcpaDeploymentPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('NcpaDeploymentPage', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.getNcpaDevices.mockResolvedValue(DEVICES)
    api.getLatestRun.mockResolvedValue(null)
    api.getRuns.mockResolvedValue({ items: [run()], page: 1, pages: 1, total: 1, hasNext: false, hasPrev: false, needsReview: 1 })
    api.getRun.mockResolvedValue(run())
  })

  it('lists devices with their trust and last result, and counts them', async () => {
    renderPage()

    const row = (await screen.findByText('nas-06')).closest('tr')!
    expect(within(row).getByText('Down')).toBeInTheDocument()
    expect(within(row).getByText('Device unreachable.')).toBeInTheDocument()
    expect(within(screen.getByText('db-02').closest('tr')!).getByText('Not verified')).toBeInTheDocument()
    expect(within(screen.getByText('web-01').closest('tr')!).getByRole('checkbox')).toBeDisabled()

    // Card titles are <p>; badges with the same words are <span>.
    const card = (title: string) => screen.getByText(title, { selector: 'p' }).parentElement!.parentElement!
    expect(card('Eligible Devices')).toHaveTextContent('4')
    expect(card('Failed')).toHaveTextContent('1')
    expect(card('Down')).toHaveTextContent('1')
    expect(screen.getByRole('tab', { name: /Deployment History/ })).toHaveTextContent('1 to review')
  })

  it('opens host-key verification for an unverified device', async () => {
    api.getLiveFingerprint.mockResolvedValue('LIVEKEY')
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'Verify' }))

    expect(screen.getByRole('dialog', { name: 'Verify host key' })).toBeInTheDocument()
    expect(await screen.findByText('SHA256:LIVEKEY')).toBeInTheDocument()
    expect(api.getLiveFingerprint).toHaveBeenCalledWith(2)
  })

  it('shows the history and marks a run reviewed', async () => {
    api.reviewRun.mockResolvedValue(run({ reviewedAt: new Date('2026-10-04T09:00:00Z'), reviewedBy: 'Admin User', needsReview: false }))
    renderPage('/ncpa-deployment?tab=history')

    fireEvent.click(await screen.findByText('NP-0011'))

    const drawer = await screen.findByRole('dialog', { name: 'Deployment NP-0011' })
    expect(await within(drawer).findByText('SSH authentication failed.')).toBeInTheDocument()
    fireEvent.click(within(drawer).getByRole('button', { name: 'Mark as reviewed' }))

    expect(await within(drawer).findByText(/Reviewed by/)).toBeInTheDocument()
    expect(api.reviewRun).toHaveBeenCalledWith(11)
  })

  it('retries the failed and down devices of a run', async () => {
    renderPage('/ncpa-deployment?tab=history&run=11')

    const drawer = await screen.findByRole('dialog', { name: 'Deployment NP-0011' })
    fireEvent.click(await within(drawer).findByRole('button', { name: 'Retry failed devices' }))

    const wizard = screen.getByRole('dialog', { name: 'Deploy NCPA' })
    const checked = within(wizard)
      .getAllByRole('checkbox')
      .filter((box) => (box as HTMLInputElement).checked)
      .map((box) => box.closest('label')!.textContent)
    expect(checked).toEqual([expect.stringContaining('app-03'), expect.stringContaining('nas-06')])
  })

  it('offers a new login for a device whose login failed', async () => {
    renderPage('/ncpa-deployment?tab=history&run=11')

    const drawer = await screen.findByRole('dialog', { name: 'Deployment NP-0011' })
    fireEvent.click(await within(drawer).findByRole('button', { name: 'Enter new login' }))

    expect(screen.getByText(/Credentials for app-03/)).toBeInTheDocument()
  })

  it('shows the running deployment and blocks starting another', async () => {
    api.getLatestRun.mockResolvedValue(
      run({ status: 'Running', progress: 30, needsReview: false, completedAt: null, devices: [
        { deviceId: 3, hostname: 'app-03', ipAddress: '10.0.20.3', outcome: 'Running', error: null },
        { deviceId: 6, hostname: 'nas-06', ipAddress: '10.0.20.6', outcome: 'Pending', error: null },
      ] }),
    )
    renderPage()

    expect(await screen.findByRole('region', { name: 'Deployment in progress' })).toHaveTextContent('0 / 2 devices')
    await waitFor(() => expect(screen.getByRole('button', { name: /Deploy NCPA/ })).toBeDisabled())
  })
})
