import { MiniSparkline } from './MiniSparkline'

const connectionsSparkline = [4200, 4500, 4400, 4700, 4600, 4850, 4800]

export function ActiveConnectionsCard() {
  return (

    <div className="flex flex-col gap-3 rounded-2xl bg-[var(--card)] border border-[var(--border)] p-5 shadow-sm">
      <span className="text-sm text-[var(--text-muted)]">Active Connections</span>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-bold text-[var(--text)]">4,850</span>
        <span className="text-sm text-[var(--text-muted)]">connections</span>
      </div>
      <MiniSparkline data={connectionsSparkline} color="#10B981" gradientId="connectionsSpark" />
    </div>
  )
}