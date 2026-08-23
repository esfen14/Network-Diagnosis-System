import { Cpu, HardDrive, MemoryStick, MoreHorizontal } from 'lucide-react'

const resources = [
  { label: 'Memory', value: '54%', icon: MemoryStick },
  { label: 'CPU Usage', value: '47%', icon: Cpu },
  { label: 'Disk', value: '32%', icon: HardDrive },
]

export function ResourceUsageCard() {
  return (
    <div className="flex h-full flex-col rounded-3xl bg-white p-5 shadow-sm">
      <div className="mb-5 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-var(--system-text)">Average Resource</h3>
        <button
          type="button"
          className="rounded-2xl bg-black/5 p-2 text-black/60 hover:bg-black/10"
          aria-label="More options"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>

      <div className="grid flex-1 content-center gap-4 sm:grid-cols-3">
        {resources.map(({ label, value, icon: Icon }) => (
          <div
            key={label}
            className="flex flex-col items-center rounded-3xl bg-gray-100 p-4"
          >
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#F4A90B]">
              <Icon className="h-5 w-5 text-white" />
            </div>
            <p className="text-sm text-var(--system-text-secondary)">{label}</p>
            <p className="mt-1 text-lg font-semibold text-var(--system-text)">{value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}