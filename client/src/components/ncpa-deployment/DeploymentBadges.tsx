import { Ban, CheckCircle2, MinusCircle, Power, XCircle } from 'lucide-react'
import type { AgentStatus, DeploymentRun, DeviceOutcome, RunCounts } from '../../types/ncpaDeployment'

const BADGE = 'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium'

const TONES = {
  green: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400',
  amber: 'bg-[#ffb100]/15 text-[#b37b00] dark:text-[#ffb100]',
  red: 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-400',
  gray: 'bg-gray-100 text-gray-600 dark:bg-white/10 dark:text-gray-400',
  blue: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
  orange: 'bg-orange-100 text-orange-700 dark:bg-orange-500/15 dark:text-orange-300',
} as const

type Tone = keyof typeof TONES

function Badge({ tone, label, pulse = false }: { tone: Tone; label: string; pulse?: boolean }) {
  return (
    <span className={`${BADGE} ${TONES[tone]}`}>
      <span className={`h-1.5 w-1.5 rounded-full bg-current ${pulse ? 'animate-pulse' : ''}`} />
      {label}
    </span>
  )
}

const OUTCOME_TONES: Record<DeviceOutcome, Tone> = {
  Pending: 'gray',
  Running: 'amber',
  Success: 'green',
  Failed: 'red',
  Down: 'gray',
  Incompatible: 'gray',
  Rejected: 'orange',
  Skipped: 'gray',
}

export function OutcomeBadge({ outcome }: { outcome: DeviceOutcome }) {
  return <Badge tone={OUTCOME_TONES[outcome]} label={outcome} pulse={outcome === 'Running'} />
}

const AGENT_LABELS: Record<AgentStatus, [Tone, string]> = {
  'Pending NCPA': ['amber', 'Pending'],
  'Deployed NCPA': ['green', 'Deployed'],
  'Deployment Failed': ['red', 'Failed'],
  Excluded: ['gray', 'Excluded'],
  Incompatible: ['gray', 'Incompatible'],
}

export function AgentStatusBadge({ status }: { status: AgentStatus | null }) {
  if (!status) return <span className="text-gray-400">—</span>
  const [tone, label] = AGENT_LABELS[status]
  return <Badge tone={tone} label={label} />
}

/** How a run reads in history: a finished, unreviewed run is "Ready for review". */
function runResult(run: Pick<DeploymentRun, 'status' | 'needsReview' | 'reviewedAt'>): { tone: Tone; label: string } {
  switch (run.status) {
    case 'Running':
      return { tone: 'amber', label: 'Running' }
    case 'Success':
      return run.reviewedAt ? { tone: 'blue', label: 'Reviewed' } : { tone: 'green', label: 'Ready for review' }
    case 'Partial Failure':
      return { tone: 'orange', label: run.reviewedAt ? 'Partial failure · reviewed' : 'Partial failure' }
    case 'Failed':
      return { tone: 'red', label: 'Failed' }
    default:
      return { tone: 'gray', label: 'Stopped' }
  }
}

export function RunResultBadge({ run }: { run: Pick<DeploymentRun, 'status' | 'needsReview' | 'reviewedAt'> }) {
  const { tone, label } = runResult(run)
  return <Badge tone={tone} label={label} pulse={run.status === 'Running'} />
}

/** Compact per-outcome counts, e.g. "✔ 3  ✖ 1  ⏻ 1"; only non-zero outcomes are shown. */
export function OutcomeCounts({ counts }: { counts: RunCounts }) {
  const parts = [
    { n: counts.success, label: 'deployed', icon: CheckCircle2, className: 'text-emerald-600 dark:text-emerald-400' },
    { n: counts.failed, label: 'failed', icon: XCircle, className: 'text-red-600 dark:text-red-400' },
    { n: counts.down, label: 'down', icon: Power, className: 'text-gray-500 dark:text-gray-400' },
    { n: counts.incompatible, label: 'incompatible', icon: Ban, className: 'text-gray-500 dark:text-gray-400' },
    { n: counts.rejected, label: 'rejected', icon: Ban, className: 'text-orange-600 dark:text-orange-300' },
    { n: counts.skipped, label: 'skipped', icon: MinusCircle, className: 'text-gray-500 dark:text-gray-400' },
  ].filter((p) => p.n > 0)

  if (parts.length === 0) return <span className="text-gray-400">—</span>

  return (
    <span className="inline-flex flex-wrap items-center gap-3 tabular-nums">
      {parts.map(({ n, label, icon: Icon, className }) => (
        <span key={label} className={`inline-flex items-center gap-1 ${className}`} title={`${n} ${label}`}>
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          <span>{n}</span>
          <span className="sr-only">{label}</span>
        </span>
      ))}
    </span>
  )
}
