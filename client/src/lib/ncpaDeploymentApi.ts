// Wrappers for the NCPA deployment routes (server/app/api/system/ncpa_deployment.py).
// Credentials are only ever sent in request bodies, never in URLs.
import { apiGet, apiPost } from './api'
import {
  fromRawDevice,
  fromRawRun,
  fromRawRunsPage,
  type CredentialCheckResult,
  type DeploymentRun,
  type DeviceCredentials,
  type NcpaDevice,
  type RawDeploymentRun,
  type RawNcpaDevice,
  type RawRunsPage,
  type RejectedDevice,
  type RunsPage,
  type StartResult,
} from '../types/ncpaDeployment'

const BASE = '/api/system/deployment/ncpa'

export const NCPA_DEPLOYMENT_STARTED_EVENT = 'nds:ncpa-deployment-started'

function credentialsBody(entries: DeviceCredentials[]) {
  return {
    devices: entries.map((e) => ({ device_id: e.deviceId, username: e.username, password: e.password })),
  }
}

export async function getNcpaDevices(): Promise<NcpaDevice[]> {
  const data = await apiGet<{ devices: RawNcpaDevice[] }>(`${BASE}/devices`)
  return data.devices.map(fromRawDevice)
}

export async function getLiveFingerprint(deviceId: number): Promise<string> {
  const data = await apiGet<{ fingerprint: string }>(`${BASE}/${deviceId}/fingerprint`)
  return data.fingerprint
}

/** Trust the key the user was shown. A 409 ApiError carries `data.fingerprint`, the new key. */
export function confirmTrust(deviceId: number, fingerprint: string): Promise<unknown> {
  return apiPost(`${BASE}/${deviceId}/confirm-trust`, { fingerprint })
}

export async function checkCredentials(
  entries: DeviceCredentials[],
): Promise<{ deviceId: number; result: CredentialCheckResult }[]> {
  const data = await apiPost<{ results: { device_id: number; result: CredentialCheckResult }[] }>(
    `${BASE}/check-credentials`,
    credentialsBody(entries),
  )
  return data.results.map((r) => ({ deviceId: r.device_id, result: r.result }))
}

/** Start a run. When every device is rejected the 400 ApiError carries `data.rejected`. */
export async function startDeployment(entries: DeviceCredentials[]): Promise<StartResult> {
  const data = await apiPost<{ run_id: number; started: number; rejected: RejectedDevice[] }>(
    `${BASE}/start`,
    credentialsBody(entries),
  )
  return { runId: data.run_id, started: data.started, rejected: data.rejected }
}

export function stopDeployment(): Promise<unknown> {
  return apiPost(`${BASE}/stop`)
}

/** The latest run, or null when no deployment has ever run. */
export async function getLatestRun(): Promise<DeploymentRun | null> {
  const data = await apiGet<RawDeploymentRun | { success: boolean } | null>(`${BASE}/status`)
  return data && 'id' in data ? fromRawRun(data) : null
}

export async function getRuns(params: {
  page: number
  perPage: number
  status?: string
  needsReview?: boolean
}): Promise<RunsPage> {
  const query = new URLSearchParams({ page: String(params.page), per_page: String(params.perPage) })
  if (params.status) query.set('status', params.status)
  if (params.needsReview) query.set('needs_review', 'true')
  return fromRawRunsPage(await apiGet<RawRunsPage>(`${BASE}/runs?${query}`))
}

export async function getRun(runId: number): Promise<DeploymentRun> {
  return fromRawRun(await apiGet<RawDeploymentRun>(`${BASE}/runs/${runId}`))
}

export async function reviewRun(runId: number): Promise<DeploymentRun> {
  return fromRawRun(await apiPost<RawDeploymentRun>(`${BASE}/runs/${runId}/review`))
}
