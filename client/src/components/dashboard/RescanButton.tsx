import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, HelpCircle, RefreshCw, X, XCircle } from 'lucide-react'
import { apiGet, apiPost, errorMessage } from '../../lib/api'

type ScanState = 'idle' | 'confirm' | 'scanning' | 'success' | 'error'

type DiscoveryStatus = {
  status: 'Queued' | 'Running' | 'Completed' | 'Failed' | 'Interrupted'
  progress: number
  message: string
  error: string | null
}

const POLL_INTERVAL_MS = 2000

export function RescanButton({
  onScanComplete,
}: {
  onScanComplete?: () => void
} = {}) {
  const [scanState, setScanState] = useState<ScanState>('idle')
  const [progress, setProgress] = useState(0)
  const [errorText, setErrorText] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [])

  const startScan = () => setScanState('confirm')
  const closeModal = () => {
    if (pollRef.current) window.clearInterval(pollRef.current)
    setScanState('idle')
  }

  const pollStatus = () => {
    pollRef.current = window.setInterval(async () => {
      try {
        const data = await apiGet<DiscoveryStatus | { message: string }>('/api/system/discover/status')
        if (!('status' in data)) return

        setProgress(data.progress)

        if (data.status === 'Completed') {
          if (pollRef.current) window.clearInterval(pollRef.current)
          setScanState('success')
          onScanComplete?.()
        } else if (data.status === 'Failed' || data.status === 'Interrupted') {
          if (pollRef.current) window.clearInterval(pollRef.current)
          setErrorText(data.error || `Discovery ${data.status.toLowerCase()}.`)
          setScanState('error')
        }
      } catch {
        // Transient poll failure — keep polling, don't surface an error yet.
      }
    }, POLL_INTERVAL_MS)
  }

  const confirmScan = async () => {
    setScanState('scanning')
    setProgress(0)
    setErrorText(null)
    try {
      await apiPost('/api/system/discover/start')
      pollStatus()
    } catch (err) {
      setErrorText(errorMessage(err, 'Unable to start network discovery.'))
      setScanState('error')
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={startScan}
        className="flex items-center gap-2 rounded-full bg-[#F4A90B] px-4 py-2 text-sm font-semibold text-white shadow-lg transition hover:brightness-105"
      >
        <RefreshCw className="h-4 w-4" />
        Rescan Network
      </button>

      {scanState !== 'idle' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="relative w-full max-w-sm rounded-3xl bg-white p-8 text-center shadow-xl">
            {scanState !== 'scanning' && (
              <button
                type="button"
                onClick={closeModal}
                aria-label="Close"
                className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            )}

            {scanState === 'confirm' && (
              <>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#F4A90B]">
                  <HelpCircle className="h-7 w-7 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Confirm Network Rescan
                </h3>
                <p className="mt-2 text-sm text-gray-500">
                  Are you sure you want to rescan the network? This action will
                  re-analyze all connected devices and update the current
                  network health status.
                </p>
                <div className="mt-6 flex justify-center gap-3">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-2xl border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={confirmScan}
                    className="rounded-2xl bg-emerald-500 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                  >
                    Confirm
                  </button>
                </div>
              </>
            )}

            {scanState === 'scanning' && (
              <>
                <div className="mx-auto mb-4 h-14 w-14 animate-spin rounded-full border-4 border-amber-200 border-t-amber-500" />
                <h3 className="text-lg font-semibold text-gray-900">
                  Scanning in Progress
                </h3>
                <p className="mt-2 text-sm text-gray-500">
                  {progress > 0 ? `${progress}% complete. ` : ''}Please wait. Do not close the system.
                </p>
              </>
            )}

            {scanState === 'success' && (
              <>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500">
                  <CheckCircle2 className="h-8 w-8 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Rescan successful!
                </h3>
                <div className="mt-6 flex justify-center">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-2xl bg-emerald-500 px-8 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                  >
                    OK
                  </button>
                </div>
              </>
            )}

            {scanState === 'error' && (
              <>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-red-500">
                  <XCircle className="h-8 w-8 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900">
                  Rescan failed
                </h3>
                <p className="mt-2 text-sm text-gray-500">{errorText}</p>
                <div className="mt-6 flex justify-center">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="rounded-2xl bg-gray-800 px-8 py-2 text-sm font-medium text-white hover:bg-gray-900"
                  >
                    Close
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
