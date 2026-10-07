// Wrappers around the pause / resume routes in server/app/api/system/device_identity.py.
import { apiPost } from './api'
import type { MonitoringState } from '../types/host'

// Like the port-edit route: the change is saved, and config_ok says whether Nagios was brought up to date.
export type MonitoringChangeResult = {
  config_applied: boolean
  config_ok: boolean
  config_message: string
  device: { id: number; monitoring_state: MonitoringState; monitored: boolean }
}

export function pauseDevice(deviceId: number) {
  return apiPost<MonitoringChangeResult>(`/api/system/hosts/${deviceId}/pause`)
}

export function resumeDevice(deviceId: number) {
  return apiPost<MonitoringChangeResult>(`/api/system/hosts/${deviceId}/resume`)
}
