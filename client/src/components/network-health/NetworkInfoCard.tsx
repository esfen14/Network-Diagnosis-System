import { Calendar, Clock, RefreshCw } from 'lucide-react'

const networkDetails = [
  { label: 'IP Range', value: '192.168.1.1 - 192.168.1.254' },
  { label: 'Gateway Device', value: 'R1 - 192.168.1.1' },
  { label: 'Subnet Mask', value: '255.255.255.0' },
  { label: 'DNS Server', value: '192.168.0.5' },
  { label: 'ISP', value: 'PLDT Enterprise Fiber' },
  { label: 'Location', value: 'Pimentel Hall, 3rd Floor' },
]

type NetworkInfoCardProps = {
  lastScanDate: string
  lastScanTime: string
  // Omitted when the user can't run a scan; the button is then disabled.
  onStartScan?: () => void
}

export function NetworkInfoCard({ lastScanDate, lastScanTime, onStartScan }: NetworkInfoCardProps) {
  return (
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
          onClick={onStartScan}
          disabled={!onStartScan}
          title={onStartScan ? undefined : "Your role can't run network scans"}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-[#0D1117] px-6 py-3.5 text-sm font-semibold text-white shadow-md transition hover:bg-black/90 active:scale-[0.99] cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RefreshCw className="h-4 w-4" />
          Rescan Network
        </button>
      </div>
    </div>
  )
}
