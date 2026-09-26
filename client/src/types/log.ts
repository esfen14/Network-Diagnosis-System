// Mirrors the five log endpoints exposed by server/app/api/system/log.py.
// All five endpoints share the same envelope shape, differing only in the
// optional `details` payload attached to non-activity categories.

export type LogCategory =
  | 'activity'
  | 'configurationChange'
  | 'networkDiscovery'
  | 'ncpaDeployment'
  | 'exportLog'

export type LogEntry = {
  id: number
  category: LogCategory
  type: string
  title: string
  user: string
  description: string
  timestamp: string
  tagId: string
  details?: Record<string, unknown>
}

export type LogListResponse = {
  items: LogEntry[]
  page: number
  per_page: number
  pages: number
  total: number
  has_next: boolean
  has_prev: boolean
}

export const LOG_ENDPOINTS: Record<LogCategory, string> = {
  activity: '/api/system/log',
  configurationChange: '/api/system/configurationchange',
  networkDiscovery: '/api/system/networkdiscovery',
  ncpaDeployment: '/api/system/ncpadeployment',
  exportLog: '/api/system/exportlog',
}
