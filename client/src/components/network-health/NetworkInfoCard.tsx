import { useState } from 'react'
import { Calendar, Clock, RefreshCw, HelpCircle, Check, Loader2, X } from 'lucide-react'

const networkDetails = [
  { label: 'IP Range', value: '192.168.1.1 - 192.168.1.254' },
  { label: 'Gateway Device', value: 'R1 - 192.168.1.1' },
  { label: 'Subnet Mask', value: '255.255.255.0' },
  { label: 'DNS Server', value: '192.168.0.5' },
  { label: 'ISP', value: 'PLDT Enterprise Fiber' },
  { label: 'Location', value: 'Pimentel Hall, 3rd Floor' },
]

export function NetworkInfoCard() {
  const [modalState, setModalState] = useState<'idle' | 'confirm' | 'scanning' | 'complete'>('idle')

  const handleStartScan = () => {
    setModalState('confirm')
  }

  const handleConfirmScan = () => {
    setModalState('scanning')
    // Simulate network scanning process for 3 seconds
    setTimeout(() => {
      setModalState('complete')
    }, 3000)
  }

  const closeModal = () => {
    setModalState('idle')
  }

  return (
    <div
      className="relative min-h-100 rounded-4xl p-8 shadow-xl"
      style={{
        background: 'linear-gradient(180deg, #F5A317 25%, #F8BB54 100%)',
      }}
    >
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
              Today
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              02:43 PM
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

      {/* White Re-Scan Button */}
      <button
        type="button"
        onClick={handleStartScan}
        className="mt-8 flex w-full items-center justify-center gap-2 rounded-3xl bg-white px-6 py-3.5 text-sm font-medium text-[#171B20] shadow-md transition hover:bg-gray-100"
      >
        <RefreshCw className="h-4 w-4" />
        Re-Scan
      </button>

      {/* --- MODAL POPUPS --- */}
      {modalState !== 'idle' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-xs">
          <div className="relative w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl">
            
            {/* Close Button (Hidden during scanning state) */}
            {modalState !== 'scanning' && (
              <button
                type="button"
                onClick={closeModal}
                className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            )}

            {/* 1. Confirmation Modal */}
            {modalState === 'confirm' && (
              <div className="text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-amber-400 text-white shadow-md">
                  <HelpCircle className="h-8 w-8" />
                </div>
                <h3 className="text-xl font-bold text-gray-800">Confirm Network Rescan</h3>
                <p className="mt-2 text-sm text-gray-500 leading-relaxed px-4">
                  Are you sure you want to rescan the network? This action will re-analyze all connected devices and update the current network health status.
                </p>
                <div className="mt-6 flex gap-3">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="flex-1 rounded-xl border border-gray-300 bg-white py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirmScan}
                    className="flex-1 rounded-xl bg-emerald-500 py-2.5 text-sm font-medium text-white shadow-md hover:bg-emerald-600"
                  >
                    Confirm
                  </button>
                </div>
              </div>
            )}

            {/* 2. Scanning Progress Modal */}
            {modalState === 'scanning' && (
              <div className="py-6 text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center">
                  <Loader2 className="h-12 w-12 animate-spin text-blue-500" />
                </div>
                <h3 className="text-xl font-bold text-gray-800">Scanning in Progress</h3>
                <p className="mt-1 text-sm text-gray-500">Please wait. Do not close the system.</p>
              </div>
            )}

            {/* 3. Completion Modal */}
            {modalState === 'complete' && (
              <div className="text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-blue-400 text-white shadow-md">
                  <Check className="h-8 w-8" />
                </div>
                <h3 className="text-xl font-bold text-gray-800">Rescan completed.</h3>
                <div className="mt-6">
                  <button
                    type="button"
                    onClick={closeModal}
                    className="w-full rounded-xl bg-emerald-500 py-2.5 text-sm font-medium text-white shadow-md hover:bg-emerald-600"
                  >
                    OK
                  </button>
                </div>
              </div>
            )}

          </div>
        </div>
      )}
    </div>
  )
}