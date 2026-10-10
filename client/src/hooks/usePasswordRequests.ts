import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../lib/api'

export type PasswordRequest = {
  id: number
  userId: number
  name: string
  email: string
  requestedAt: Date
}

type RawRequest = {
  id: number
  user_id: number
  name: string
  email: string
  requested_at: string
}

const POLL_INTERVAL_MS = 30_000

// Pending forgot-password requests, for users allowed to handle them
// (account.edit). Polls so a new request shows up in the bell without a reload.
export function usePasswordRequests(enabled: boolean) {
  const [requests, setRequests] = useState<PasswordRequest[]>([])

  const reload = useCallback(async () => {
    try {
      const data = await apiGet<{ items: RawRequest[] }>('/api/user/password-requests')
      setRequests(
        data.items.map((r) => ({
          id: r.id,
          userId: r.user_id,
          name: r.name,
          email: r.email,
          requestedAt: new Date(r.requested_at),
        })),
      )
    } catch {
      // Keep the last list; the next poll retries.
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    reload()
    const id = window.setInterval(reload, POLL_INTERVAL_MS)
    return () => window.clearInterval(id)
  }, [enabled, reload])

  return { requests, reload }
}
