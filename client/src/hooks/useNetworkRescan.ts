import { useEffect, useRef, useState } from 'react'
import { ApiError, apiGet, apiPost, errorMessage } from '../lib/api'

// Runs a real network discovery scan (POST /api/system/discover/start) in the
// background and polls its status until it finishes. There is no dialog:
// callers show `state` on their button (spinner while scanning) and
// `errorText` inline. Shared by the Dashboard and the Network Health page.

export type RescanState = 'idle' | 'scanning' | 'success' | 'error'

type DiscoveryStatusResponse = {
  status: 'Running' | 'Success' | 'Failed' | 'Interrupted'
  progress: number
  message: string
  error: string | null
}

const POLL_INTERVAL_MS = 2000

export function useNetworkRescan(onComplete?: () => void) {
  const [state, setState] = useState<RescanState>('idle')
  const [progress, setProgress] = useState(0)
  const [errorText, setErrorText] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)
  const onCompleteRef = useRef(onComplete)

  useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  const stopPolling = () => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  useEffect(() => stopPolling, [])

  const pollStatus = () => {
    stopPolling()
    pollRef.current = window.setInterval(async () => {
      try {
        const data = await apiGet<DiscoveryStatusResponse | null>('/api/system/discover/status')
        if (!data || !('status' in data)) return

        setProgress(data.progress)

        if (data.status === 'Success') {
          stopPolling()
          setState('success')
          onCompleteRef.current?.()
        } else if (data.status === 'Failed' || data.status === 'Interrupted') {
          stopPolling()
          setErrorText(data.error || `Discovery ${data.status.toLowerCase()}.`)
          setState('error')
          onCompleteRef.current?.()
        }
      } catch {
        // Transient poll failure — keep polling, don't surface an error yet.
      }
    }, POLL_INTERVAL_MS)
  }

  const start = async () => {
    if (state === 'scanning') return
    setState('scanning')
    setProgress(0)
    setErrorText(null)
    try {
      await apiPost('/api/system/discover/start')
      pollStatus()
    } catch (err) {
      // Someone else's scan is already running: follow that one instead.
      if (err instanceof ApiError && err.status === 400 && /already running/i.test(err.message)) {
        pollStatus()
        return
      }
      setErrorText(errorMessage(err, 'Unable to start network discovery.'))
      setState('error')
    }
  }

  const dismissError = () => {
    setErrorText(null)
    if (state === 'error') setState('idle')
  }

  return { state, progress, errorText, start, dismissError }
}
