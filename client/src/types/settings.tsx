// PLEASE WALANG GAGALAW NG KAHIT ANO DITO

export type Theme = 'dark' | 'light'

export type FontSize = 'small' | 'medium' | 'large'

export type DashboardLayout =
  | 'default'
  | 'compact'
  | 'expanded'

export type UpdateFrequency =
  | 'weekly'
  | 'monthly'
  | 'quarterly'
  | 'manual'

export type SecurityFrequency =
  | 'daily'
  | 'weekly'
  | 'monthly'

export interface SystemSettings {
  // General
  systemLanguage: string
  theme: Theme

  timeZone: string
  dateTimeFormat: string

  systemFont: string
  systemFontSize: FontSize

  // Dashboard / diagnostics
  dashboardRefreshRate: number
  scanFrequency: number
  dashboardLayout: DashboardLayout

  // Notifications
  notifications: boolean

  // Export
  exportFormats: string[]

  // Security
  sessionTimeout: number
  strongPasswordPolicy: boolean
  failedLoginMonitoring: boolean
  auditLogging: boolean
  securityCheckFrequency: SecurityFrequency

  // System
  systemUpdateFrequency: UpdateFrequency
  maintenanceMode: boolean
  automaticBackups: boolean

  // Data retention
  logRetentionDays: number
  diagnosticHistoryRetentionDays: number

  // Concurrency — required so PUT /api/settings can detect
  // if someone else saved since we last fetched. Always sent
  // back to the server on save; the server rejects (409) if
  // it doesn't match the row's current version.
  version: number
}