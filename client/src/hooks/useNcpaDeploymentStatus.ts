import { useCallback, useEffect, useRef, useState } from 'react'
import { errorMessage } from '../lib/api'
import { getLatestRun, NCPA_DEPLOYMENT_STARTED_EVENT, stopDeployment } from '../lib/ncpaDeploymentApi'
import type { DeploymentRun } from '../types/ncpaDeployment'

const RUNNING_POLL_MS = 2000
const IDLE_POLL_MS = 15_000

// Polls the latest NCPA deployment run: every 2 s while it runs, every 15 s
// otherwise. hasUnseenResult turns on when a run this hook watched finishes,
// so the header bell can show a dot until the panel is opened. The wizard
// dispatches NCPA_DEPLOYMENT_STARTED_EVENT so polling speeds up at once.
export function useNcpaDeploymentStatus(enabled: boolean) {
  const [run, setRun] = useState<DeploymentRun | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)
  const [hasUnseenResult, setHasUnseenResult] = useState(false)
  const lastStatusRef = useRef<string | null>(null)
  const timeoutRef = useRef<number | null>(null)
  const pollRef = useRef<() => void>(() => {})

  const poll = useCallback(async () => {
    if (timeoutRef.current) window.clearTimeout(timeoutRef.current)

    let running = lastStatusRef.current === 'Running'
    try {
      const latest = await getLatestRun()
      if (latest) {
        running = latest.status === 'Running'
        if (lastStatusRef.current === 'Running' && !running) setHasUnseenResult(true)
        if (!running) setIsCancelling(false)
        lastStatusRef.current = latest.status
      }
      setRun(latest)
    } catch {
      // Keep the last known run; the next poll retries.
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
      // The new run is Running from the moment /start returns.
      lastStatusRef.current = 'Running'
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current)
      pollRef.current()
    }
    window.addEventListener(NCPA_DEPLOYMENT_STARTED_EVENT, onStarted)

    return () => {
      window.removeEventListener(NCPA_DEPLOYMENT_STARTED_EVENT, onStarted)
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current)
    }
  }, [enabled])

  const cancel = async () => {
    setIsCancelling(true)
    setCancelError(null)
    try {
      await stopDeployment()
      poll()
    } catch (err) {
      setIsCancelling(false)
      setCancelError(errorMessage(err, 'Unable to stop the deployment.'))
    }
  }

  const markSeen = () => setHasUnseenResult(false)

  return { run, isCancelling, cancelError, hasUnseenResult, cancel, markSeen, refresh: poll }
}
