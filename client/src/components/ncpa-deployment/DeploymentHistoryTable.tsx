import { useEffect, useState } from 'react'
import { History } from 'lucide-react'
import { errorMessage } from '../../lib/api'
import { getRuns } from '../../lib/ncpaDeploymentApi'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'
import { formatDateTime } from '../../utils/formatDateTime'
import { runTag, type DeploymentRun } from '../../types/ncpaDeployment'
import { OutcomeCounts, RunResultBadge } from './DeploymentBadges'

const PER_PAGE = 10

// Result filter: the run statuses plus "Ready for review".
const FILTERS = [
  { id: 'all', label: 'All results' },
  { id: 'review', label: 'Ready for review' },
  { id: 'Success', label: 'Success' },
  { id: 'Partial Failure', label: 'Partial failure' },
  { id: 'Failed', label: 'Failed' },
  { id: 'Interrupted', label: 'Stopped' },
  { id: 'Running', label: 'Running' },
] as const

type FilterId = (typeof FILTERS)[number]['id']

type Props = {
  // Bumped by the page when a run starts, finishes or is reviewed.
  refreshKey: number
  onSelectRun: (runId: number) => void
}

function duration(run: DeploymentRun) {
  if (!run.completedAt) return '—'
  const seconds = Math.max(0, Math.round((run.completedAt.getTime() - run.startAt.getTime()) / 1000))
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`
}

// "Deployment History" tab: every run, newest first, with its result and
// how each device ended. Clicking a run opens its details.
export function DeploymentHistoryTable({ refreshKey, onSelectRun }: Props) {
  const { settings } = useSystemSettings()
  const [filter, setFilter] = useState<FilterId>('all')
  const [page, setPage] = useState(1)
  const [runs, setRuns] = useState<DeploymentRun[]>([])
  const [meta, setMeta] = useState({ pages: 1, total: 0, hasNext: false, hasPrev: false })
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getRuns({
      page,
      perPage: PER_PAGE,
      status: filter === 'all' || filter === 'review' ? undefined : filter,
      needsReview: filter === 'review',
    })
      .then((data) => {
        if (cancelled) return
        setRuns(data.items)
        setMeta({ pages: data.pages, total: data.total, hasNext: data.hasNext, hasPrev: data.hasPrev })
        setLoadError(null)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(errorMessage(err, 'Unable to load deployment history.'))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [page, filter, refreshKey])

  return (
    <section className="overflow-hidden rounded-2xl bg-white shadow-sm dark:bg-[#171B20]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 p-4 dark:border-white/10">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Deployment History</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Every deployment run and what happened to each device. Finished runs stay “Ready for review” until someone
            reviews them.
          </p>
        </div>
        <select
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value as FilterId)
            setPage(1)
          }}
          aria-label="Filter by result"
          className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 dark:border-white/10 dark:bg-[#0D1117] dark:text-white"
        >
          {FILTERS.map((f) => (
            <option key={f.id} value={f.id}>{f.label}</option>
          ))}
        </select>
      </div>

      {loadError && (
        <div className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
          {loadError}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-225 text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-xs text-gray-500 dark:border-white/10 dark:text-gray-500">
              <th className="px-4 py-3 font-normal">Run</th>
              <th className="px-4 py-3 font-normal">Started</th>
              <th className="px-4 py-3 font-normal">Started By</th>
              <th className="px-4 py-3 font-normal">Duration</th>
              <th className="px-4 py-3 font-normal">Result</th>
              <th className="px-4 py-3 font-normal">Devices</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && runs.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">Loading history…</td>
              </tr>
            ) : runs.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-gray-500 dark:text-gray-400">
                  <History className="mx-auto mb-2 h-5 w-5 opacity-60" />
                  {filter === 'all' ? 'No deployments have run yet.' : 'No deployments match this filter.'}
                </td>
              </tr>
            ) : (
              runs.map((run) => (
                <tr
                  key={run.id}
                  tabIndex={0}
                  onClick={() => onSelectRun(run.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onSelectRun(run.id)
                    }
                  }}
                  className="cursor-pointer border-b border-gray-100 transition hover:bg-gray-50 focus:bg-gray-50 focus:outline-none dark:border-white/5 dark:hover:bg-white/5 dark:focus:bg-white/5"
                >
                  <td className="px-4 py-3 font-medium tabular-nums text-gray-900 dark:text-white">{runTag(run.id)}</td>
                  <td className="px-4 py-3 tabular-nums text-gray-600 dark:text-gray-300">
                    {formatDateTime(run.startAt, settings.dateTimeFormat, settings.timeZone)}
                  </td>
                  <td className="px-4 py-3 text-gray-600 dark:text-gray-300">{run.startedBy ?? '—'}</td>
                  <td className="px-4 py-3 tabular-nums text-gray-600 dark:text-gray-300">{duration(run)}</td>
                  <td className="px-4 py-3"><RunResultBadge run={run} /></td>
                  <td className="px-4 py-3"><OutcomeCounts counts={run.counts} /></td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t border-gray-200 px-4 py-3 text-sm text-gray-500 dark:border-white/10 dark:text-gray-400">
        <span>
          Page {page} of {meta.pages} · {meta.total} runs total
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setPage((p) => p - 1)}
            disabled={!meta.hasPrev}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10"
          >
            Previous
          </button>
          <span className="rounded-lg border border-gray-200 bg-white px-3 py-1 text-gray-900 shadow-sm dark:border-transparent dark:bg-white/10 dark:text-white">
            {page}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={!meta.hasNext}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10"
          >
            Next
          </button>
        </div>
      </div>
    </section>
  )
}
