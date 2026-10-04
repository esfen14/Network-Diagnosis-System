import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2, Eye, KeyRound, RotateCcw, X } from 'lucide-react'
import { errorMessage } from '../../lib/api'
import { getRun, reviewRun } from '../../lib/ncpaDeploymentApi'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'
import { formatDateTime } from '../../utils/formatDateTime'
import { runTag, type DeploymentRun, type NcpaDevice } from '../../types/ncpaDeployment'
import { OutcomeBadge, OutcomeCounts, RunResultBadge } from './DeploymentBadges'

const AUTH_FAILED = 'SSH authentication failed.'

type Props = {
  runId: number
  devices: NcpaDevice[]
  isRunning: boolean
  onClose: () => void
  // Called after the run was marked reviewed.
  onChanged: () => void
  onRetry: (deviceIds: number[]) => void
  onNewLogin: (deviceId: number) => void
}

// Details of one deployment run: its result, each device's outcome and
// reason, and the review action.
export function DeploymentRunDrawer({ runId, devices, isRunning, onClose, onChanged, onRetry, onNewLogin }: Props) {
  const { settings } = useSystemSettings()
  const [run, setRun] = useState<DeploymentRun | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [isReviewing, setIsReviewing] = useState(false)

  useEffect(() => {
    let cancelled = false
    getRun(runId)
      .then((data) => {
        if (!cancelled) setRun(data)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(errorMessage(err, 'Unable to load this deployment.'))
      })
    return () => {
      cancelled = true
    }
  }, [runId])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const markReviewed = async () => {
    setIsReviewing(true)
    setReviewError(null)
    try {
      setRun(await reviewRun(runId))
      onChanged()
    } catch (err) {
      setReviewError(errorMessage(err, 'Unable to mark this deployment as reviewed.'))
    } finally {
      setIsReviewing(false)
    }
  }

  // Only devices that can still be deployed to are offered for retry.
  const deployable = new Set(devices.filter((d) => d.deployable).map((d) => d.id))
  const retryIds = run
    ? run.devices.filter((d) => (d.outcome === 'Failed' || d.outcome === 'Down') && deployable.has(d.deviceId)).map((d) => d.deviceId)
    : []
  const finished = run !== null && run.status !== 'Running'
  const reviewable = run !== null && (run.status === 'Success' || run.status === 'Partial Failure')
  const durationText =
    run?.completedAt != null
      ? `${Math.max(0, Math.round((run.completedAt.getTime() - run.startAt.getTime()) / 1000))}s`
      : '—'

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/50"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div role="dialog" aria-modal="true" aria-labelledby="ncpa-run-title" className="h-full w-full max-w-xl overflow-y-auto bg-white shadow-xl dark:bg-[#171B20]">
        <div className="sticky top-0 flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4 dark:border-white/10 dark:bg-[#171B20]">
          <h2 id="ncpa-run-title" className="text-lg font-semibold text-gray-900 dark:text-white">
            Deployment {runTag(runId)}
          </h2>
          <button type="button" onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-6 p-6">
          {loadError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
              {loadError}
            </div>
          )}
          {!run && !loadError && <p className="text-sm text-gray-500">Loading deployment…</p>}

          {run && (
            <>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Started {formatDateTime(run.startAt, settings.dateTimeFormat, settings.timeZone)}
                {run.startedBy ? ` by ${run.startedBy}` : ''}. {run.message}
              </p>

              <dl className="grid grid-cols-3 gap-3">
                <div className="rounded-xl bg-gray-50 p-3 dark:bg-white/5">
                  <dt className="text-[11px] uppercase tracking-wide text-gray-500">Result</dt>
                  <dd className="mt-1"><RunResultBadge run={run} /></dd>
                </div>
                <div className="rounded-xl bg-gray-50 p-3 dark:bg-white/5">
                  <dt className="text-[11px] uppercase tracking-wide text-gray-500">Duration</dt>
                  <dd className="mt-1 text-sm font-semibold tabular-nums text-gray-900 dark:text-white">{durationText}</dd>
                </div>
                <div className="rounded-xl bg-gray-50 p-3 dark:bg-white/5">
                  <dt className="text-[11px] uppercase tracking-wide text-gray-500">Devices</dt>
                  <dd className="mt-1 text-sm"><OutcomeCounts counts={run.counts} /></dd>
                </div>
              </dl>

              {run.status === 'Failed' && run.error && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
                  {run.error}
                </div>
              )}

              {reviewable && (
                <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 p-4 dark:border-white/10">
                  {run.reviewedAt ? (
                    <span className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      Reviewed by <b>{run.reviewedBy ?? 'an administrator'}</b> ·{' '}
                      {formatDateTime(run.reviewedAt, settings.dateTimeFormat, settings.timeZone)}
                    </span>
                  ) : (
                    <>
                      <span className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                        <Eye className="h-4 w-4 shrink-0" />
                        Check the device results below, then mark this run reviewed.
                      </span>
                      <button
                        type="button"
                        onClick={markReviewed}
                        disabled={isReviewing}
                        className="inline-flex items-center gap-2 rounded-lg bg-[#ffb100] px-3 py-1.5 text-sm font-semibold text-gray-900 hover:bg-[#f0a500] disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        {isReviewing ? 'Saving…' : 'Mark as reviewed'}
                      </button>
                    </>
                  )}
                  {reviewError && <p role="alert" className="w-full text-sm text-red-600 dark:text-red-400">{reviewError}</p>}
                </div>
              )}

              <div>
                <h3 className="mb-3 text-sm font-semibold text-gray-900 dark:text-white">Device results</h3>
                {run.devices.length === 0 ? (
                  <p className="text-sm text-gray-500">This run has no per-device results. Runs before this page existed did not record them.</p>
                ) : (
                  <ul className="divide-y divide-gray-100 overflow-hidden rounded-xl border border-gray-200 dark:divide-white/5 dark:border-white/10">
                    {run.devices.map((d) => (
                      <li key={d.deviceId} className="flex flex-wrap items-center gap-3 px-4 py-3">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-gray-900 dark:text-white">
                            {d.hostname} <span className="font-normal text-gray-500">· {d.ipAddress}</span>
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            {d.outcome === 'Success' ? (
                              <>
                                NCPA installed and responding. Its checks appear in{' '}
                                <Link to="/network-health" className="font-medium text-[#b37b00] hover:underline dark:text-[#ffb100]">
                                  Network Health
                                </Link>
                                .
                              </>
                            ) : (
                              d.error ?? ''
                            )}
                          </p>
                        </div>
                        {finished && !isRunning && d.outcome === 'Failed' && d.error === AUTH_FAILED && deployable.has(d.deviceId) && (
                          <button
                            type="button"
                            onClick={() => onNewLogin(d.deviceId)}
                            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-100 dark:border-white/10 dark:text-gray-200 dark:hover:bg-white/10"
                          >
                            <KeyRound className="h-3.5 w-3.5" /> Enter new login
                          </button>
                        )}
                        <OutcomeBadge outcome={d.outcome} />
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {finished && retryIds.length > 0 && (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    {retryIds.length} device{retryIds.length === 1 ? '' : 's'} failed or {retryIds.length === 1 ? 'was' : 'were'} down.
                  </span>
                  <button
                    type="button"
                    onClick={() => onRetry(retryIds)}
                    disabled={isRunning}
                    title={isRunning ? 'A deployment is already running.' : undefined}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:border-white/20 dark:text-gray-200 dark:hover:bg-white/10"
                  >
                    <RotateCcw className="h-4 w-4" /> Retry failed devices
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
