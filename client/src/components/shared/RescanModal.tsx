import { CheckCircle2, HelpCircle, X, XCircle } from 'lucide-react'
import type { RescanState } from '../../hooks/useNetworkRescan'

// Confirm / progress / result dialog for a network rescan. Driven by
// useNetworkRescan(); used by the Dashboard and Network Health pages.
export function RescanModal({
  state,
  progress,
  errorText,
  onConfirm,
  onClose,
}: {
  state: RescanState
  progress: number
  errorText: string | null
  onConfirm: () => void
  onClose: () => void
}) {
  return (
    <>
      {state !== 'idle' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="relative w-full max-w-sm rounded-3xl bg-white p-8 text-center shadow-xl">
            {state !== 'scanning' && (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            )}

            {state === 'confirm' && (
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
                    onClick={onClose}
                    className="rounded-2xl border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={onConfirm}
                    className="rounded-2xl bg-emerald-500 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                  >
                    Confirm
                  </button>
                </div>
              </>
            )}

            {state === 'scanning' && (
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

            {state === 'success' && (
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
                    onClick={onClose}
                    className="rounded-2xl bg-emerald-500 px-8 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                  >
                    OK
                  </button>
                </div>
              </>
            )}

            {state === 'error' && (
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
                    onClick={onClose}
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
