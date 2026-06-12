import { Cpu, HardDrive, MemoryStick, MoreHorizontal } from 'lucide-react'

const resources = [
  { label: 'Memory', value: '54%', icon: MemoryStick },
  { label: 'CPU Usage', value: '47%', icon: Cpu },
  { label: 'Disk', value: '32%', icon: HardDrive },
]

export function ResourceUsageCard() {
  return (
    <div className="rounded-3xl bg-[#171B20] p-5 shadow-sm">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">Average Resource</h3>
        <button
          type="button"
          className="rounded-2xl bg-white/10 p-2 text-white/70 hover:bg-white/20"
          aria-label="More options"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {resources.map(({ label, value, icon: Icon }) => (
          <div
            key={label}
            className="flex flex-col items-center rounded-3xl bg-[#232323] p-4"
          >
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#F4A90B]">
              <Icon className="h-5 w-5 text-white" />
            </div>
            <p className="text-sm text-gray-400">{label}</p>
            <p className="mt-1 text-lg font-semibold text-white">{value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
