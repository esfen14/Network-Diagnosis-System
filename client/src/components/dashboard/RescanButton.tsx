import { RefreshCw } from 'lucide-react'
import { useNetworkRescan } from '../../hooks/useNetworkRescan'
import { RescanModal } from '../shared/RescanModal'

export function RescanButton({
  onScanComplete,
}: {
  onScanComplete?: () => void
} = {}) {
  const rescan = useNetworkRescan(onScanComplete)

  return (
    <>
      <button
        type="button"
        onClick={rescan.open}
        className="flex items-center gap-2 rounded-full bg-[#F4A90B] px-4 py-2 text-sm font-semibold text-white shadow-lg transition hover:brightness-105"
      >
        <RefreshCw className="h-4 w-4" />
        Rescan Network
      </button>

      <RescanModal
        state={rescan.state}
        progress={rescan.progress}
        errorText={rescan.errorText}
        onConfirm={rescan.confirm}
        onClose={rescan.close}
      />
    </>
  )
}
