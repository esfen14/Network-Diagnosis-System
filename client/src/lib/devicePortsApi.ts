// Wrappers around the device port routes in server/app/api/system/device_identity.py.
import { apiGet, apiPut } from './api'
import type { DevicePortsResponse, PortChange, PortChangeResult, PortProtocol } from '../types/devicePorts'

export function getDevicePorts(deviceId: number) {
  return apiGet<DevicePortsResponse>(`/api/system/hosts/${deviceId}/ports`)
}

// One request for every action: Monitor, Ignore, Stop, Leave suggested, Resume, Acknowledge,
// Set service and Remove pin are all bodies of the same route (see devicePortsLogic.requestFor).
export function changePort(deviceId: number, protocol: PortProtocol, port: number, change: PortChange) {
  return apiPut<PortChangeResult>(`/api/system/hosts/${deviceId}/ports/${protocol}/${port}`, change)
}
