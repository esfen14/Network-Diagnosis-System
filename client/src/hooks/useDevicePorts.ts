import { useCallback, useEffect, useState } from 'react'
import { errorMessage } from '../lib/api'
import { getDevicePorts } from '../lib/devicePortsApi'
import type { DevicePortsResponse } from '../types/devicePorts'

type Loaded = { deviceId: number; data: DevicePortsResponse }
type Failure = { key: string; message: string }

// Loads a device's ports and reloads on demand. State is only set when an answer arrives, and each
// answer is tagged with the device (and the load) it belongs to, so:
//   - a slow answer for a device that is no longer shown is ignored, and one device never shows
//     another's ports;
//   - the previous list stays on screen while a reload is in flight, so it does not flicker after
//     an action;
//   - an error belongs to one load and is gone as soon as the next load starts.
export function useDevicePorts(deviceId: number) {
  const [loaded, setLoaded] = useState<Loaded | null>(null)
  const [failure, setFailure] = useState<Failure | null>(null)
  const [settledKey, setSettledKey] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const key = `${deviceId}:${reloadKey}`

  useEffect(() => {
    let cancelled = false
    getDevicePorts(deviceId)
      .then((response) => {
        if (cancelled) return
        setLoaded({ deviceId, data: response })
        setSettledKey(key)
      })
      .catch((err) => {
        if (cancelled) return
        setFailure({ key, message: errorMessage(err, 'Unable to load the ports.') })
        setSettledKey(key)
      })
    return () => {
      cancelled = true
    }
  }, [deviceId, key])

  const reload = useCallback(() => setReloadKey((current) => current + 1), [])

  return {
    data: loaded?.deviceId === deviceId ? loaded.data : null,
    error: failure?.key === key ? failure.message : null,
    isLoading: settledKey !== key,
    reload,
  }
}
