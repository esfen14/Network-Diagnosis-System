// Wording, styles and filter options for a device's monitoring state
// (spec files/Device_Inventory_Requirements.md, "Monitoring state"). The server decides the state;
// this only says how to show it.
import type { MonitoringState } from '../../types/host'

export const MONITORING_LABELS: Record<MonitoringState, string> = {
  monitored: 'Monitored',
  missing: 'Missing',
  address_unknown: 'Address unknown',
  paused: 'Paused',
  retired: 'Retired',
  merged: 'Merged',
}

export const MONITORING_REASONS: Record<MonitoringState, string> = {
  monitored: 'Nagios is checking this device.',
  missing: 'Not seen in the last few scans. It is still being checked, so Nagios reports it as down.',
  address_unknown: 'Its address now belongs to another device. Checks are off until it is found again.',
  paused: 'An administrator paused monitoring. Scans still track the device, but Nagios does not check it.',
  retired: 'Retired: Nagios no longer checks it. The status shown is the last one Nagios reported.',
  merged: 'Merged into another device: Nagios no longer checks it. The status shown is the last one Nagios reported.',
}

export const MONITORING_STYLES: Record<MonitoringState, string> = {
  monitored: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  missing: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  address_unknown: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  paused: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  retired: 'bg-gray-500/15 text-[var(--text-muted)]',
  merged: 'bg-gray-500/15 text-[var(--text-muted)]',
}

// A retired or merged device is out of the Nagios config, so its host row is a stale snapshot.
export function isStaleSnapshot(state: MonitoringState | null) {
  return state === 'retired' || state === 'merged'
}

// Pause and resume only make sense for a device that is still in the config or paused out of it.
export function canPauseOrResume(state: MonitoringState | null) {
  return state !== null && !isStaleSnapshot(state)
}

export type MonitoringFilter = 'all' | 'not_monitored' | MonitoringState

export const MONITORING_FILTERS: { value: MonitoringFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'monitored', label: 'Monitored' },
  { value: 'not_monitored', label: 'Not monitored' },
  { value: 'missing', label: 'Missing' },
  { value: 'address_unknown', label: 'Address unknown' },
  { value: 'paused', label: 'Paused' },
  { value: 'retired', label: 'Retired' },
  { value: 'merged', label: 'Merged' },
]
