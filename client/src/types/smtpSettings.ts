// Gmail is the only provider: smtp.gmail.com, port 587, STARTTLS.
export type SmtpPreset = {
  provider: 'gmail'
  host: string
  port: number
  tls: 'starttls'
}

// The saved settings. The password is write-only: the server only says whether one is saved.
export type SmtpSettings = SmtpPreset & {
  username: string
  sender: string
  passwordSet: boolean
  configured: boolean
  version: number
  updatedAt: string | null
}

export type SmtpSettingsResponse = {
  settings: SmtpSettings
  presets: { gmail: SmtpPreset }
}

export type SmtpSaveValues = {
  username: string
  sender: string
  // Sent exactly as typed. Left out to keep the saved one.
  password?: string
}

export type SmtpTestResult =
  | { ok: true; recipient: string }
  | {
      ok: false
      // auth_failed (rejected login), connect_failed (blocked port), host_not_found, tls_failed, rejected, send_failed.
      code: string
      message: string
      // The mail server's own text.
      details: string
    }
