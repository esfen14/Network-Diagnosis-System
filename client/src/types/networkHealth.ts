// Mirrors server/app/api/system/network_health.py's summary endpoint.
// (trends/plugins are covered by types/dashboard.ts's TrendsResponse, which
// this page reuses.)
import { fromCountBlock, type CountBlock } from './dashboard'

export type NetworkHealthSummary = {
  hosts: CountBlock
  services: CountBlock
  activeAlerts: { total: number; critical: number; warning: number; unknown: number }
}

type CountBlockRecord = Record<string, number>

type NetworkHealthSummaryApiResponse = {
  hosts: CountBlockRecord
  services: CountBlockRecord
  active_alerts: { total: number; critical: number; warning: number; unknown: number }
}

export function fromNetworkHealthSummaryResponse(
  data: NetworkHealthSummaryApiResponse
): NetworkHealthSummary {
  return {
    hosts: fromCountBlock(data.hosts),
    services: fromCountBlock(data.services),
    activeAlerts: data.active_alerts,
  }
}
