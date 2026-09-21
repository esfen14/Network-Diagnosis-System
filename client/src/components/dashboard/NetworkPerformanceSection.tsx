import { MoreHorizontal } from 'lucide-react'
import { MetricCard } from './MetricCard'
import { NetworkChart } from './NetworkChart'

export function NetworkPerformanceSection() {
  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--text)]">Network Performance</h2>
        <button type="button" className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]" aria-label="More options">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      <div className="mb-6 grid grid-cols-3 gap-3">
        <MetricCard label="Latency" value="12.5 ms" status="Excellent" />
        <MetricCard label="Packets Loss" value="0.3%" status="Normal" />
        <MetricCard label="Bandwidth" value="850 mbps" status="Excellent" />
      </div>
      <NetworkChart />
    </div>
  )
}