// Wire records from /api/system/deployment/ncpa/* and the view models the
// NCPA Deployment page uses. See spec files/NCPA_Deployment_UI_Plan.md §6.

import { serverDate } from '../utils/formatDateTime'
export type RunStatus = 'Running' | 'Success' | 'Partial Failure' | 'Failed' | 'Interrupted'

export type DeviceOutcome =
  | 'Pending'
  | 'Running'
  | 'Success'
  | 'Failed'
  | 'Down'
  | 'Incompatible'
  | 'Rejected'
  | 'Skipped'

export type AgentStatus = 'Pending NCPA' | 'Deployed NCPA' | 'Deployment Failed' | 'Excluded' | 'Incompatible'

export type CredentialCheckResult =
  | 'ok'
  | 'auth_failed'
  | 'no_sudo'
  | 'unreachable'
  | 'host_key_changed'
  | 'not_trusted'
  | 'not_found'
  | 'rate_limited'

export type RawNcpaDevice = {
  device_id: number
  hostname: string
  ip_address: string
  trusted: boolean
  fingerprint: string | null
  agent_status: AgentStatus | null
  last_error: string | null
  last_outcome: DeviceOutcome | null
  last_run_id: number | null
  deployable: boolean
}

export type NcpaDevice = {
  id: number
  hostname: string
  ipAddress: string
  trusted: boolean
  fingerprint: string | null
  agentStatus: AgentStatus | null
  lastError: string | null
  lastOutcome: DeviceOutcome | null
  lastRunId: number | null
  deployable: boolean
}

export type RunCounts = {
  pending: number
  running: number
  success: number
  failed: number
  down: number
  incompatible: number
  rejected: number
  skipped: number
}

export type RawDeviceResult = {
  device_id: number
  hostname: string | null
  ip_address: string | null
  outcome: DeviceOutcome
  error: string | null
  started_at: string | null
  completed_at: string | null
}

export type DeviceResult = {
  deviceId: number
  hostname: string
  ipAddress: string
  outcome: DeviceOutcome
  error: string | null
}

export type RawDeploymentRun = {
  id: number
  status: RunStatus
  progress: number
  message: string
  error: string | null
  start_at: string
  completed_at: string | null
  started_by: string | null
  counts: RunCounts
  reviewed_at: string | null
  reviewed_by: string | null
  needs_review: boolean
  devices?: RawDeviceResult[]
}

export type DeploymentRun = {
  id: number
  status: RunStatus
  progress: number
  message: string
  error: string | null
  startAt: Date
  completedAt: Date | null
  startedBy: string | null
  counts: RunCounts
  reviewedAt: Date | null
  reviewedBy: string | null
  needsReview: boolean
  devices: DeviceResult[]
}

export type RawRunsPage = {
  items: RawDeploymentRun[]
  page: number
  per_page: number
  pages: number
  total: number
  has_next: boolean
  has_prev: boolean
  needs_review: number
}

export type RunsPage = {
  items: DeploymentRun[]
  page: number
  pages: number
  total: number
  hasNext: boolean
  hasPrev: boolean
  needsReview: number
}

export type RejectedDevice = { device_id: number; reason: string }

export type StartResult = { runId: number; started: number; rejected: RejectedDevice[] }

export type DeviceCredentials = { deviceId: number; username: string; password: string }

export function fromRawDevice(raw: RawNcpaDevice): NcpaDevice {
  return {
    id: raw.device_id,
    hostname: raw.hostname,
    ipAddress: raw.ip_address,
    trusted: raw.trusted,
    fingerprint: raw.fingerprint,
    agentStatus: raw.agent_status,
    lastError: raw.last_error,
    lastOutcome: raw.last_outcome,
    lastRunId: raw.last_run_id,
    deployable: raw.deployable,
  }
}

export function fromRawResult(raw: RawDeviceResult): DeviceResult {
  return {
    deviceId: raw.device_id,
    hostname: raw.hostname ?? `Device ${raw.device_id}`,
    ipAddress: raw.ip_address ?? '—',
    outcome: raw.outcome,
    error: raw.error,
  }
}

export function fromRawRun(raw: RawDeploymentRun): DeploymentRun {
  return {
    id: raw.id,
    status: raw.status,
    progress: raw.progress,
    message: raw.message,
    error: raw.error,
    startAt: serverDate(raw.start_at),
    completedAt: raw.completed_at ? serverDate(raw.completed_at) : null,
    startedBy: raw.started_by,
    counts: raw.counts,
    reviewedAt: raw.reviewed_at ? serverDate(raw.reviewed_at) : null,
    reviewedBy: raw.reviewed_by,
    needsReview: raw.needs_review,
    devices: (raw.devices ?? []).map(fromRawResult),
  }
}

export function fromRawRunsPage(raw: RawRunsPage): RunsPage {
  return {
    items: raw.items.map(fromRawRun),
    page: raw.page,
    pages: raw.pages,
    total: raw.total,
    hasNext: raw.has_next,
    hasPrev: raw.has_prev,
    needsReview: raw.needs_review,
  }
}

/** The run ID as System Logs shows it, e.g. "NP-0008". */
export function runTag(id: number): string {
  return `NP-${String(id).padStart(4, '0')}`
}

/** How many devices a run has finished, of those it actually tried. */
export function runProgressCounts(run: DeploymentRun) {
  const tried = run.devices.filter((d) => d.outcome !== 'Rejected')
  const done = tried.filter((d) => d.outcome !== 'Pending' && d.outcome !== 'Running').length
  return { done, total: tried.length }
}

/** "3 deployed, 1 failed, 1 down" — used in notifications. */
export function describeCounts(counts: RunCounts): string {
  return [
    counts.success && `${counts.success} deployed`,
    counts.failed && `${counts.failed} failed`,
    counts.down && `${counts.down} down`,
    counts.incompatible && `${counts.incompatible} incompatible`,
    counts.rejected && `${counts.rejected} rejected`,
    counts.skipped && `${counts.skipped} skipped`,
  ]
    .filter(Boolean)
    .join(', ')
}
