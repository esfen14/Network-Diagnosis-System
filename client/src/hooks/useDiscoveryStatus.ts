import { useCallback, useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, errorMessage } from '../lib/api'

export type DiscoveryRunStatus = 'Running' | 'Success' | 'Failed' | 'Interrupted'

export type DiscoveryStatus = {
  id: number
  status: DiscoveryRunStatus
  progress: number
  message: string
  startAt: Date
  completedAt: Date | null
  error: string | null
}

type RawDiscoveryStatus = {
  id: number
  status: DiscoveryRunStatus
  progress: number
  message: string
  start_at: string
  completed_at: string | null
  error: string | null
}

export const DISCOVERY_STARTED_EVENT = 'nds:discovery-started'

const RUNNING_POLL_MS = 2000
const IDLE_POLL_MS = 15_000
const MAX_PENDING_POLLS = 5

export function useDiscoveryStatus(enabled: boolean) {
  const [scan, setScan] = useState<DiscoveryStatus | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)
  const [hasUnseenResult, setHasUnseenResult] = useState(false)
  const lastStatusRef = useRef<DiscoveryRunStatus | null>(null)
  const lastIdRef = useRef<number | null>(null)
  const pendingPollsRef = useRef(0)
  const timeoutRef = useRef<number | null>(null)
  const pollRef = useRef<() => void>(() => {})

  const poll = useCallback(async () => {
    if (timeoutRef.current) window.clearTimeout(timeoutRef.current)

    let running = lastStatusRef.current === 'Running'
    try {
      const data = await apiGet<RawDiscoveryStatus | null>('/api/system/discover/status')
      const isPreviousRun =
        pendingPollsRef.current > 0 && data && 'status' in data &&
        data.id === lastIdRef.current && data.status !== 'Running'
      if (isPreviousRun) {
        pendingPollsRef.current -= 1
        running = pendingPollsRef.current > 0
      } else if (data && 'status' in data) {
        pendingPollsRef.current = 0
        running = data.status === 'Running'
        if (lastStatusRef.current === 'Running' && !running) setHasUnseenResult(true)
        if (!running) setIsCancelling(false)
        lastStatusRef.current = data.status
        lastIdRef.current = data.id
        setScan({
          id: data.id,
          status: data.status,
          progress: data.progress,
          message: data.message,
          startAt: new Date(data.start_at),
          completedAt: data.completed_at ? new Date(data.completed_at) : null,
          error: data.error,
        })
      }
    } catch {
    }

    timeoutRef.current = window.setTimeout(() => pollRef.current(), running ? RUNNING_POLL_MS : IDLE_POLL_MS)
  }, [])

  useEffect(() => {
    pollRef.current = poll
  }, [poll])

  useEffect(() => {
    if (!enabled) return

    pollRef.current()
    const onStarted = () => {
      pendingPollsRef.current = MAX_PENDING_POLLS
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current)
      timeoutRef.current = window.setTimeout(() => pollRef.current(), RUNNING_POLL_MS)
    }
    window.addEventListener(DISCOVERY_STARTED_EVENT, onStarted)

    return () => {
      window.removeEventListener(DISCOVERY_STARTED_EVENT, onStarted)
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current)
    }
  }, [enabled])

  const cancel = async () => {
    setIsCancelling(true)
    setCancelError(null)
    try {
      await apiPost('/api/system/network-discovery/stop')
      poll()
    } catch (err) {
      setIsCancelling(false)
      setCancelError(errorMessage(err, 'Unable to cancel the scan.'))
    }
  }

  const markSeen = () => setHasUnseenResult(false)

  return { scan, isCancelling, cancelError, hasUnseenResult, cancel, markSeen }
}
