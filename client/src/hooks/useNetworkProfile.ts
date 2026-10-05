import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiPut } from '../lib/api'

export type NetworkProfile = {
  name: string
  reference: string
  details: { label: string; value: string }[]
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
    const saved = await apiPut<NetworkProfile>('/api/system/network-profile', next)
    setProfile(saved)
  }, [])

  return { profile, save }
}
