// Wrappers around server/app/api/system/smtp_settings.py.
import { apiGet, apiPost, apiPut } from './api'
import type { SmtpSaveValues, SmtpSettings, SmtpSettingsResponse, SmtpTestResult } from '../types/smtpSettings'

export function getSmtpSettings() {
  return apiGet<SmtpSettingsResponse>('/api/system/smtp-settings')
}

export function saveSmtpSettings(values: SmtpSaveValues, version: number) {
  return apiPut<SmtpSettings>('/api/system/smtp-settings', { provider: 'gmail', ...values, version })
}

export function sendTestEmail() {
  return apiPost<SmtpTestResult>('/api/system/smtp-settings/test')
}
