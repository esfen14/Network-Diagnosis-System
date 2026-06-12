import { MoreHorizontal } from 'lucide-react'

const columns = ['Processes', 'Users', 'Process Load', 'User Activity', 'Peek Processes', 'Session Change']
const values = ['135/device', '2-4/device', 'Normal', '310 processes', 'Moderate', '+2 users']
const barWidths = [72, 45, 60, 85, 55, 38]

export function SystemActivityCard() {
  return (
    <div className="rounded-3xl bg-[#171B20] p-5 shadow-sm">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">System Activity</h3>
        <button
          type="button"
          className="rounded-2xl bg-white/10 p-2 text-white/70 hover:bg-white/20"
          aria-label="More options"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      <div className="overflow-x-auto">
        <div className="min-w-[600px]">
          <div className="mb-3 grid grid-cols-6 gap-2">
            {columns.map((col) => (
              <span key={col} className="text-xs text-gray-500">
                {col}
              </span>
            ))}
          </div>
          <div className="mb-4 grid grid-cols-6 gap-2">
            {values.map((val, i) => (
              <span key={i} className="text-sm text-white">
                {val}
              </span>
            ))}
          </div>
          <div className="space-y-2">
            {barWidths.map((width, i) => (
              <div key={i} className="h-2 overflow-hidden rounded-full bg-white/10">
                <div
                  className="h-full rounded-full bg-white/60"
                  style={{ width: `${width}%` }}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-[#F4A90B]" />
        <span className="text-xs text-gray-400">Live monitoring active</span>
      </div>
    </div>
  )
}
