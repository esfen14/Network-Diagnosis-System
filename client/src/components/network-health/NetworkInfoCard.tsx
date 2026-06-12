import { Calendar, Clock, RefreshCw } from 'lucide-react'

const networkDetails = [
  { label: 'IP Range', value: '192.168.1.1 - 192.168.1.254' },
  { label: 'Gateway Device', value: 'R1 - 192.168.1.1' },
  { label: 'Subnet Mask', value: '255.255.255.0' },
  { label: 'DNS Server', value: '192.168.0.5' },
  { label: 'ISP', value: 'PLDT Enterprise Fiber' },
  { label: 'Location', value: 'Pimentel Hall, 3rd Floor' },
]

export function NetworkInfoCard() {
    return (
    <div
      className="min-h-[400px] rounded-[32px] p-8 shadow-xl"
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

      <button
        type="button"
        className="mt-6 flex items-center gap-2 rounded-3xl bg-[#0D1117] px-6 py-3 text-sm font-medium text-white shadow-md transition hover:bg-black"
      >
        <RefreshCw className="h-4 w-4" />
        Re-Scan
      </button>
    </div>
  )
}
