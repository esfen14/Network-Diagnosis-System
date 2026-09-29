import { RefreshCw } from 'lucide-react'
import { useNetworkRescan } from '../../hooks/useNetworkRescan'

// Starts a network scan straight away; it runs in the background and the
// button spins until it finishes. A failure is shown under the button.
export function RescanButton({
  onScanComplete,
}: {
  onScanComplete?: () => void
} = {}) {
  const rescan = useNetworkRescan(onScanComplete)
  const isScanning = rescan.state === 'scanning'

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={rescan.start}
        disabled={isScanning}
        className="flex items-center gap-2 rounded-full bg-[#F4A90B] px-4 py-2 text-sm font-semibold text-white shadow-lg transition hover:brightness-105 disabled:cursor-default disabled:hover:brightness-100"
      >
        <RefreshCw className={`h-4 w-4 ${isScanning ? 'animate-spin' : ''}`} />
        {isScanning ? `Scanning…${rescan.progress > 0 ? ` ${rescan.progress}%` : ''}` : 'Rescan Network'}
      </button>
      {rescan.errorText && (
        <p role="alert" className="text-xs text-red-600 dark:text-red-400">
          Rescan failed: {rescan.errorText}
        </p>
      )}
    </div>
  )
}
