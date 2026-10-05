import { Loader2 } from 'lucide-react'
import { runProgressCounts, runTag, type DeploymentRun } from '../../types/ncpaDeployment'
import { OutcomeBadge } from './DeploymentBadges'

type Props = {
  run: DeploymentRun
  isCancelling: boolean
  cancelError: string | null
  onCancel: () => void
}

// Shown above the tabs while a run is going: progress, each device's state
// and a Stop button.
export function DeploymentRunBanner({ run, isCancelling, cancelError, onCancel }: Props) {
  const { done, total } = runProgressCounts(run)
  const tried = run.devices.filter((d) => d.outcome !== 'Rejected')

  return (
    <section
      aria-label="Deployment in progress"
      className="space-y-3 rounded-2xl border border-[#ffb100]/30 bg-[#ffb100]/10 p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
          <Loader2 className="h-4 w-4 animate-spin text-[#ffb100]" />
          {isCancelling ? 'Stopping NCPA deployment…' : 'NCPA deployment in progress'}
          <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs font-medium text-gray-600 dark:bg-white/10 dark:text-gray-300">
            {runTag(run.id)}
          </span>
        </span>
        <span className="flex items-center gap-3">
          <span className="text-sm tabular-nums text-gray-600 dark:text-gray-300">
            {done} / {total} devices
          </span>
          <button
            type="button"
            onClick={onCancel}
            disabled={isCancelling}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-700 hover:border-red-300 hover:text-red-600 disabled:cursor-default disabled:opacity-50 dark:border-white/20 dark:bg-transparent dark:text-gray-200"
          >
            {isCancelling ? 'Stopping…' : 'Stop'}
          </button>
        </span>
      </div>
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-white/70 dark:bg-white/10"
        role="progressbar"
        aria-label="Deployment progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={run.progress}
      >
        <div className="h-full rounded-full bg-[#ffb100] transition-all" style={{ width: `${run.progress}%` }} />
      </div>
      <div className="flex justify-between gap-2 text-xs text-gray-600 dark:text-gray-400">
        <span className="truncate">{run.message}</span>
        <span className="shrink-0 tabular-nums">{run.progress}%</span>
      </div>
      {tried.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {tried.map((d) => (
            <li
              key={d.deviceId}
              className="inline-flex items-center gap-2 rounded-full border border-gray-200 bg-white px-3 py-1 text-xs dark:border-white/10 dark:bg-[#171B20]"
            >
              <span className="font-medium text-gray-900 dark:text-white">{d.hostname}</span>
              <OutcomeBadge outcome={d.outcome} />
            </li>
          ))}
        </ul>
      )}
      {cancelError && <p role="alert" className="text-xs text-red-600 dark:text-red-400">{cancelError}</p>}
    </section>
  )
}
