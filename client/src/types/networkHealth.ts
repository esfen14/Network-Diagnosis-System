// Mirrors server/app/api/system/network_health.py's summary endpoint.
// (trends/plugins are covered by types/dashboard.ts's TrendsResponse, which
// this page reuses.)
import { fromCountBlock, type CountBlock } from './dashboard'

export type NetworkHealthSummary = {
  hosts: CountBlock
  services: CountBlock
  activeAlerts: { total: number; critical: number; warning: number; unknown: number }
  // Last successful network discovery scan — shared by every user.
  lastScan: { completedAt: Date | null; isRunning: boolean }
}

type CountBlockRecord = Record<string, number>

type NetworkHealthSummaryApiResponse = {
  hosts: CountBlockRecord
  services: CountBlockRecord
  active_alerts: { total: number; critical: number; warning: number; unknown: number }
  last_scan?: { completed_at: string | null; is_running: boolean }
}

export function fromNetworkHealthSummaryResponse(
  data: NetworkHealthSummaryApiResponse
): NetworkHealthSummary {
  return {
    hosts: fromCountBlock(data.hosts),
    services: fromCountBlock(data.services),
    activeAlerts: data.active_alerts,
    lastScan: {
      completedAt: data.last_scan?.completed_at ? new Date(data.last_scan.completed_at) : null,
      isRunning: data.last_scan?.is_running ?? false,
    },
  }
}
