import { MoreHorizontal } from 'lucide-react'
import { MetricCard } from './MetricCard'
import { NetworkChart } from './NetworkChart'
import type { PingMetrics, TrendPoint } from '../../types/dashboard'

type NetworkPerformanceSectionProps = {
  pingMetrics: PingMetrics | null
  rtaTrend: TrendPoint[]
  isLoading: boolean
}

function latencyStatus(avgRtaMs: number | null): { label: string; color: string } {
  if (avgRtaMs == null) return { label: 'No data', color: 'text-[var(--text-muted)]' }
  if (avgRtaMs < 50) return { label: 'Excellent', color: 'text-emerald-600' }
  if (avgRtaMs < 150) return { label: 'Fair', color: 'text-amber-600' }
  return { label: 'Poor', color: 'text-red-600' }
}

function packetLossStatus(pct: number | null): { label: string; color: string } {
  if (pct == null) return { label: 'No data', color: 'text-[var(--text-muted)]' }
  if (pct < 1) return { label: 'Normal', color: 'text-emerald-600' }
  if (pct < 5) return { label: 'Elevated', color: 'text-amber-600' }
  return { label: 'High', color: 'text-red-600' }
}

export function NetworkPerformanceSection({ pingMetrics, rtaTrend, isLoading }: NetworkPerformanceSectionProps) {
  const latency = latencyStatus(pingMetrics?.avgRtaMs ?? null)
  const packetLoss = packetLossStatus(pingMetrics?.avgPacketLossPct ?? null)

  return (
    <div className="rounded-2xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--text)]">Network Performance</h2>
        <button type="button" className="rounded-xl bg-[var(--card-alt)] p-2 text-[var(--text-muted)] hover:bg-[var(--hover)]" aria-label="More options">
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </div>
      <div className="mb-6 grid grid-cols-2 gap-3">
        <MetricCard
          label="Latency"
          value={pingMetrics?.avgRtaMs != null ? `${pingMetrics.avgRtaMs} ms` : '—'}
          status={latency.label}
          statusColor={latency.color}
        />
        <MetricCard
          label="Packet Loss"
          value={pingMetrics?.avgPacketLossPct != null ? `${pingMetrics.avgPacketLossPct}%` : '—'}
          status={packetLoss.label}
          statusColor={packetLoss.color}
        />
      </div>
      <NetworkChart data={rtaTrend} isLoading={isLoading} />
    </div>
  )
}
