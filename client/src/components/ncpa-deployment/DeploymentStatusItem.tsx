import { AlertTriangle, CheckCircle2, ServerCog, XCircle } from 'lucide-react'
import { formatRelativeTime } from '../../types/notification'
import { describeCounts, runProgressCounts, runTag, type DeploymentRun } from '../../types/ncpaDeployment'

type Props = {
  run: DeploymentRun
  isCancelling: boolean
  cancelError: string | null
  onCancel: () => void
  onReview: (runId: number) => void
}

// The NCPA deployment entry of the header notification panel: live progress
// and a Stop button while a run is going, then its outcome with a link to
// review it in Deployment History.
export function DeploymentStatusItem({ run, isCancelling, cancelError, onCancel, onReview }: Props) {
  if (run.status === 'Running') {
    const { done, total } = runProgressCounts(run)
    return (
      <div className="border-b border-gray-100 bg-[#ffb100]/5 px-4 py-3 dark:border-white/10">
        <div className="flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-white">
            <ServerCog className="h-4 w-4 animate-pulse text-[#ffb100]" />
            {isCancelling ? 'Stopping NCPA deployment…' : 'NCPA deployment in progress'}
          </span>
          <button
            type="button"
            onClick={onCancel}
            disabled={isCancelling}
            className="rounded-lg border border-gray-200 px-2 py-0.5 text-xs font-medium text-gray-600 hover:border-red-300 hover:text-red-500 disabled:cursor-default disabled:opacity-50 disabled:hover:border-gray-200 disabled:hover:text-gray-600 dark:border-white/10 dark:text-gray-300"
          >
            {isCancelling ? 'Stopping…' : 'Stop'}
          </button>
        </div>
        <div
          className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-white/10"
          role="progressbar"
          aria-label="NCPA deployment progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={run.progress}
        >
          <div className="h-full rounded-full bg-[#ffb100] transition-all" style={{ width: `${run.progress}%` }} />
        </div>
        <div className="mt-1 flex justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
          <span className="truncate">{done} of {total} devices · {run.message}</span>
          <span className="shrink-0">{run.progress}%</span>
        </div>
        {cancelError && (
          <p role="alert" className="mt-1 text-xs text-red-600 dark:text-red-400">{cancelError}</p>
        )}
      </div>
    )
  }

  const summary = describeCounts(run.counts)
  const tried = run.devices.filter((d) => d.outcome !== 'Rejected').length
  const outcome = {
    Success: {
      icon: <CheckCircle2 className="h-4 w-4 text-green-500" />,
      title: run.reviewedAt ? 'NCPA deployed · reviewed' : 'NCPA deployed: ready for review',
      body: `${run.counts.success} of ${tried} device${tried === 1 ? '' : 's'} deployed.`,
    },
    'Partial Failure': {
      icon: <AlertTriangle className="h-4 w-4 text-amber-500" />,
      title: 'NCPA deployed with problems',
      body: `${summary}.`,
    },
    Failed: {
      icon: <XCircle className="h-4 w-4 text-red-500" />,
      title: 'NCPA deployment failed',
      body: run.error ?? (summary ? `${summary}.` : run.message),
    },
    Interrupted: {
      icon: <XCircle className="h-4 w-4 text-gray-400" />,
      title: 'NCPA deployment stopped',
      body: `Stopped after ${tried - run.counts.skipped} of ${tried} devices.`,
    },
  }[run.status]

  const finishedAt = run.completedAt ?? run.startAt

  return (
    <div className="border-b border-gray-100 px-4 py-3 dark:border-white/10">
      <span className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-white">
        {outcome.icon}
        {outcome.title}
      </span>
      <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{outcome.body}</p>
      <div className="mt-1 flex items-center justify-between gap-2">
        <p className="text-[11px] text-gray-400 dark:text-gray-500">
          {runTag(run.id)} · {formatRelativeTime(Math.floor(finishedAt.getTime() / 1000))}
        </p>
        <button
          type="button"
          onClick={() => onReview(run.id)}
          className="text-xs font-medium text-[#b37b00] hover:underline dark:text-[#ffb100]"
        >
          {run.status === 'Interrupted' ? 'View run' : 'Review'} →
        </button>
      </div>
    </div>
  )
}
