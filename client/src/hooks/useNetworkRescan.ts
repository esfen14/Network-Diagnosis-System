import { useEffect, useRef, useState } from 'react'
import { ApiError, apiGet, apiPost, errorMessage } from '../lib/api'
import { DISCOVERY_STARTED_EVENT } from './useDiscoveryStatus'

export type RescanState = 'idle' | 'scanning' | 'success' | 'error'

type DiscoveryStatusResponse = {
  id: number
  status: 'Running' | 'Success' | 'Failed' | 'Interrupted'
  progress: number
  message: string
  error: string | null
}

const POLL_INTERVAL_MS = 2000
const MAX_POLLS_FOR_NEW_RUN = 5

export function useNetworkRescan(onComplete?: () => void) {
  const [state, setState] = useState<RescanState>('idle')
  const [progress, setProgress] = useState(0)
  const [errorText, setErrorText] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)
  const pollCountRef = useRef(0)
  const previousRunIdRef = useRef<number | null>(null)
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
    pollCountRef.current = 0
    pollRef.current = window.setInterval(async () => {
      try {
        const data = await apiGet<DiscoveryStatusResponse | null>('/api/system/discover/status')
        pollCountRef.current += 1
        if (!data || !('status' in data)) return

        const isPreviousRun =
          data.status !== 'Running' &&
          data.id === previousRunIdRef.current &&
          pollCountRef.current < MAX_POLLS_FOR_NEW_RUN
        if (isPreviousRun) return

        setProgress(data.progress)

        if (data.status === 'Success') {
          stopPolling()
          setState('success')
          onCompleteRef.current?.()
        } else if (data.status === 'Interrupted') {
          stopPolling()
          setState('idle')
          onCompleteRef.current?.()
        } else if (data.status === 'Failed') {
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
    previousRunIdRef.current = null
    try {
      const previous = await apiGet<DiscoveryStatusResponse | null>('/api/system/discover/status')
      if (previous && typeof previous.id === 'number') previousRunIdRef.current = previous.id
    } catch {
      // No previous run id; any new run counts as the rescan.
    }
    try {
      await apiPost('/api/system/discover/start')
      window.dispatchEvent(new CustomEvent(DISCOVERY_STARTED_EVENT))
      pollStatus()
    } catch (err) {
      if (err instanceof ApiError && err.status === 400 && /already running/i.test(err.message)) {
        window.dispatchEvent(new CustomEvent(DISCOVERY_STARTED_EVENT))
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
