import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { DeployWizard } from '../components/ncpa-deployment/DeployWizard'
import { ApiError } from '../lib/api'
import type { NcpaDevice } from '../types/ncpaDeployment'

const api = vi.hoisted(() => ({
  getLiveFingerprint: vi.fn(),
  confirmTrust: vi.fn(),
  checkCredentials: vi.fn(),
  startDeployment: vi.fn(),
}))

vi.mock('../lib/ncpaDeploymentApi', () => ({
  ...api,
  NCPA_DEPLOYMENT_STARTED_EVENT: 'nds:ncpa-deployment-started',
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

const web = device(1, 'web-01')
const app = device(3, 'app-03')
const db = device(2, 'db-02', { trusted: false, fingerprint: null })
const deployed = device(9, 'done-09', { agentStatus: 'Deployed NCPA', deployable: false })

function renderWizard(props: Partial<React.ComponentProps<typeof DeployWizard>> = {}) {
  const handlers = { onClose: vi.fn(), onDevicesChanged: vi.fn(), onStarted: vi.fn() }
  render(<DeployWizard devices={[web, app, db, deployed]} initialSelection={null} {...handlers} {...props} />)
  return handlers
}

const next = () => fireEvent.click(screen.getByRole('button', { name: /^(Next|Check logins|Deploy NCPA|Done)$/ }))
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

describe('DeployWizard', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    // jsdom has no layout, so scrollIntoView does not exist there.
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('lists only deployable devices and needs at least one selected', () => {
    renderWizard()

    expect(screen.getByText('web-01')).toBeInTheDocument()
    expect(screen.queryByText('done-09')).not.toBeInTheDocument()

    for (const name of ['web-01', 'app-03', 'db-02']) {
      fireEvent.click(within(screen.getByText(name).closest('label')!).getByRole('checkbox'))
    }
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('marks an unreachable device Down and lets the rest continue', async () => {
    api.getLiveFingerprint.mockRejectedValue(new ApiError('Could not reach device.', 502))
    renderWizard({ initialSelection: [1, 2] })
    next()

    expect(await screen.findByText(/Could not reach 10.0.20.2 on port 22/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
  })

  it('trusts exactly the key shown, and shows a new key when it changed', async () => {
    api.getLiveFingerprint.mockResolvedValue('SHOWNKEY')
    api.confirmTrust.mockRejectedValueOnce(new ApiError('Host key changed; verify again.', 409, { fingerprint: 'NEWKEY' }))
    const { onDevicesChanged } = renderWizard({ initialSelection: [2] })
    next()

    fireEvent.click(await screen.findByRole('button', { name: 'Trust' }))
    expect(api.confirmTrust).toHaveBeenCalledWith(2, 'SHOWNKEY')
    expect(await screen.findByText(/The key changed while you were looking/)).toBeInTheDocument()
    expect(screen.getByText('SHA256:NEWKEY')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()

    api.confirmTrust.mockResolvedValueOnce({})
    fireEvent.click(screen.getByRole('button', { name: 'Trust' }))
    await waitFor(() => expect(api.confirmTrust).toHaveBeenLastCalledWith(2, 'NEWKEY'))
    await waitFor(() => expect(onDevicesChanged).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
  })

  it('asks for a different login only for the device that rejected the shared one', async () => {
    api.checkCredentials
      .mockResolvedValueOnce([
        { deviceId: 1, result: 'ok' },
        { deviceId: 3, result: 'auth_failed' },
      ])
      .mockResolvedValueOnce([{ deviceId: 3, result: 'ok' }])
    renderWizard({ initialSelection: [1, 3], startStep: 2 })

    type('SSH username', 'admin')
    type('Password', 'shared-pass')
    next()

    expect(await screen.findByText(/Rejected this username or password/)).toBeInTheDocument()
    expect(api.checkCredentials).toHaveBeenCalledWith([
      { deviceId: 1, username: 'admin', password: 'shared-pass' },
      { deviceId: 3, username: 'admin', password: 'shared-pass' },
    ])
    // The banner names the device, and only app-03 gets its own labelled fields.
    expect(screen.getByRole('alert')).toHaveTextContent('1 device needs attention: app-03')
    expect(screen.getByLabelText('Username for app-03')).toBeInTheDocument()
    expect(screen.queryByLabelText('Username for web-01')).not.toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Username for app-03')).toHaveFocus())
    screen.getByLabelText('SSH username').focus()
    fireEvent.click(within(screen.getByRole('alert')).getByRole('button', { name: 'app-03' }))
    expect(screen.getByLabelText('Username for app-03')).toHaveFocus()
    expect(screen.getByRole('button', { name: 'Check logins' })).toBeDisabled()

    type('Username for app-03', 'ops')
    type('Password for app-03', 'app-pass')
    next()

    // Only the device that still needs checking is checked again.
    await waitFor(() =>
      expect(api.checkCredentials).toHaveBeenLastCalledWith([{ deviceId: 3, username: 'ops', password: 'app-pass' }]),
    )
    expect(await screen.findByRole('button', { name: 'Next' })).toBeEnabled()
    next()

    expect(screen.getByText(/logs in as admin$/)).toBeInTheDocument()
    expect(screen.getByText(/logs in as ops \(own login\)/)).toBeInTheDocument()
  })

  it('clears a check when its login is edited', async () => {
    api.checkCredentials.mockResolvedValue([{ deviceId: 1, result: 'ok' }])
    renderWizard({ initialSelection: [1], startStep: 2 })
    type('SSH username', 'admin')
    type('Password', 'p')
    next()
    expect(await screen.findByText('Login and sudo verified.')).toBeInTheDocument()

    type('Password', 'changed')

    expect(screen.queryByText('Login and sudo verified.')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check logins' })).toBeEnabled()
  })

  it('lets a device that is down be removed, and says it was left out', async () => {
    api.checkCredentials.mockResolvedValue([
      { deviceId: 1, result: 'ok' },
      { deviceId: 3, result: 'unreachable' },
    ])
    renderWizard({ initialSelection: [1, 3], startStep: 2 })
    type('SSH username', 'admin')
    type('Password', 'p')
    next()

    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }))
    next()

    expect(screen.getByText(/Deploy NCPA to/)).toHaveTextContent('Deploy NCPA to 1 device.')
    expect(screen.getByText(/Not included: app-03 \(removed\)/)).toBeInTheDocument()
  })

  it('starts the run with each device login and announces it', async () => {
    api.checkCredentials.mockResolvedValue([{ deviceId: 1, result: 'ok' }])
    api.startDeployment.mockResolvedValue({ runId: 12, started: 1, rejected: [] })
    const started = vi.fn()
    window.addEventListener('nds:ncpa-deployment-started', started)
    const { onStarted } = renderWizard({ initialSelection: [1], startStep: 2 })

    type('SSH username', 'admin')
    type('Password', 'p')
    next()
    await screen.findByText('Login and sudo verified.')
    next()
    next()

    await waitFor(() => expect(onStarted).toHaveBeenCalledWith({ runId: 12, started: 1, rejected: [] }))
    expect(api.startDeployment).toHaveBeenCalledWith([{ deviceId: 1, username: 'admin', password: 'p' }])
    expect(started).toHaveBeenCalled()
    window.removeEventListener('nds:ncpa-deployment-started', started)
  })

  it('shows why each device was rejected when nothing could start', async () => {
    api.checkCredentials.mockResolvedValue([{ deviceId: 1, result: 'ok' }])
    api.startDeployment.mockRejectedValue(
      new ApiError('No devices could be deployed.', 400, { rejected: [{ device_id: 1, reason: 'Host key mismatch.' }] }),
    )
    const { onStarted } = renderWizard({ initialSelection: [1], startStep: 2 })
    type('SSH username', 'admin')
    type('Password', 'p')
    next()
    await screen.findByText('Login and sudo verified.')
    next()
    next()

    expect(await screen.findByText('web-01: Host key mismatch.')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('No devices could be deployed.')
    expect(onStarted).not.toHaveBeenCalled()
  })

  it('names the device when only one is being deployed', () => {
    renderWizard({ initialSelection: [3], startStep: 2 })
    expect(screen.getByText(/Credentials for app-03/)).toBeInTheDocument()
  })
})
