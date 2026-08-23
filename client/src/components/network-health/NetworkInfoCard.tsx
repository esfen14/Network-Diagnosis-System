import { Calendar, Clock, CheckCircle2, HelpCircle, RefreshCw, X } from 'lucide-react'
import { useState } from 'react'

const networkDetails = [
  { label: 'IP Range', value: '192.168.1.1 - 192.168.1.254' },
  { label: 'Gateway Device', value: 'R1 - 192.168.1.1' },
  { label: 'Subnet Mask', value: '255.255.255.0' },
  { label: 'DNS Server', value: '192.168.0.5' },
  { label: 'ISP', value: 'PLDT Enterprise Fiber' },
  { label: 'Location', value: 'Pimentel Hall, 3rd Floor' },
]

type ScanState = 'idle' | 'confirm' | 'scanning' | 'success'

type NetworkInfoCardProps = {
  lastScanTime?: string
  lastScanDate?: string
  onStartScan?: () => void
}

export function NetworkInfoCard({
  lastScanTime = '02:43 PM',
  lastScanDate = 'Today',
  onStartScan,
}: NetworkInfoCardProps = {}) {
  const [internalScanState, setInternalScanState] = useState<ScanState>('idle')

  const isControlled = typeof onStartScan === 'function'
  const startScan = isControlled ? onStartScan : () => setInternalScanState('confirm')
  const closeModal = () => setInternalScanState('idle')
  const confirmScan = () => {
    setInternalScanState('scanning')
    setTimeout(() => setInternalScanState('success'), 2500)
  }

  const scanState = internalScanState

  return (
    <>
      <div
        className="flex min-h-[400px] flex-col justify-between rounded-[32px] p-8 shadow-xl"
        style={{ background: 'linear-gradient(180deg, #F5A317 25%, #F8BB54 100%)' }}
      >
        <div>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold text-white">CICT Network</h2>
              <p className="text-sm text-white/80">#AP455698</p>
            </div>
            <div className="text-right">
              <p className="text-sm font-semibold text-white">Last Scan</p>
              <div className="mt-1 flex items-center justify-end gap-3 text-sm text-white/80">
                <span className="flex items-center gap-1">
                  <Calendar className="h-3.5 w-3.5" />
                  {lastScanDate}
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  {lastScanTime}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {networkDetails.map(({ label, value }) => (
              <div key={label}>
                <p className="text-sm font-semibold text-white">{label}</p>
                <p className="text-sm text-white/80">{value}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Full-width scan button placed neatly at bottom */}
        <div className="pt-8">
          <button
            type="button"
            onClick={startScan}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-[#0D1117] px-6 py-3.5 text-sm font-semibold text-white shadow-md transition hover:bg-black/90 active:scale-[0.99] cursor-pointer"
          >
            <RefreshCw className="h-4 w-4" />
            Rescan Network
          </button>
        </div>
      </div>

      {/* Scan modal */}
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
                <h3 className="text-lg font-semibold text-gray-900">Confirm Network Rescan</h3>
                <p className="mt-2 text-sm text-gray-500">
                  Are you sure you want to rescan the network? This will re-analyze all connected
                  devices and update the current network health status.
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
                <div className="mx-auto mb-4 h-14 w-14 animate-spin rounded-full border-4 border-blue-200 border-t-blue-500" />
                <h3 className="text-lg font-semibold text-gray-900">Scanning in Progress</h3>
                <p className="mt-2 text-sm text-gray-500">Please wait. Do not close the system.</p>
              </>
            )}

            {scanState === 'success' && (
              <>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-blue-500">
                  <CheckCircle2 className="h-8 w-8 text-white" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900">Rescan successful!</h3>
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
          </div>
        </div>
      )}
    </>
  )
}
