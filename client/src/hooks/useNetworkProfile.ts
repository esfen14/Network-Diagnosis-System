import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiPut } from '../lib/api'

export type NetworkProfile = {
  name: string
  reference: string
  // derived rows are worked out by the server and cannot be edited
  details: { label: string; value: string; derived?: boolean }[]
}

export const DEFAULT_NETWORK_NAME = 'CICT Network'

export function useNetworkProfile() {
  const [profile, setProfile] = useState<NetworkProfile | null>(null)

  useEffect(() => {
    let cancelled = false
    apiGet<NetworkProfile>('/api/system/network-profile')
      .then((data) => {
        if (!cancelled && data?.name) setProfile(data)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  const save = useCallback(async (next: NetworkProfile) => {
    const editable = { ...next, details: next.details.filter((d) => !d.derived) }
    const saved = await apiPut<NetworkProfile>('/api/system/network-profile', editable)
    setProfile(saved)
  }, [])

  return { profile, save }
}
