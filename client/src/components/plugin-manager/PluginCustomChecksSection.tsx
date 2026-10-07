import { useCallback, useEffect, useState } from 'react'
import { Loader2, Pause, Pencil, Play, Plus, Search, Trash2 } from 'lucide-react'
import { errorMessage } from '../../lib/api'
import {
  addCustomCheck,
  changeCustomCheck,
  getCustomChecks,
  pauseCustomCheck,
  removeCustomCheck,
  resumeCustomCheck,
} from '../../lib/pluginApi'
import type {
  CustomCheckField,
  CustomCheckInput,
  CustomCheckItem,
  ServiceStatusKind,
} from '../../types/plugin'
import { CustomCheckDialog } from './CustomCheckDialog'

type Props = {
  pluginId: number
  pluginName: string
  fields: CustomCheckField[]
  // Called after a check was added, changed, paused, resumed or removed, so the drawer's counts reload.
  onChanged: () => void | Promise<void>
}

const PER_PAGE = 5

const STATUS_STYLES: Record<ServiceStatusKind, string> = {
  ok: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  warning: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  critical: 'bg-red-500/15 text-red-600 dark:text-red-400',
  unknown: 'bg-gray-500/15 text-gray-600 dark:text-gray-300',
  waiting: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  stale: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  stopped: 'bg-gray-400/15 text-gray-500 dark:text-gray-400',
  paused: 'bg-gray-400/15 text-gray-500 dark:text-gray-400',
}

const STATUS_LABELS: Record<ServiceStatusKind, string> = {
  ok: 'OK',
  warning: 'Warning',
  critical: 'Critical',
  unknown: 'Unknown',
  waiting: 'Waiting',
  stale: 'No recent data',
  stopped: 'Stopped',
  paused: 'Paused',
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

// The arguments of a check as the person typed them, for a one-line summary.
function summarize(check: CustomCheckItem, fields: CustomCheckField[]) {
  return fields
    .filter((field) => check.variables[field.name])
    .map((field) => `${field.flag} ${check.variables[field.name]}`)
    .join('  ')
}

export function PluginCustomChecksSection({ pluginId, pluginName, fields, onChanged }: Props) {
  const [query, setQuery] = useState('')
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const [page, setPage] = useState(1)
  const [items, setItems] = useState<CustomCheckItem[]>([])
  const [meta, setMeta] = useState({ pages: 1, total: 0, hasNext: false, hasPrev: false })
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  // The dialog: "add" opens it empty, a check opens it to change that check.
  const [dialog, setDialog] = useState<'add' | CustomCheckItem | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [dialogError, setDialogError] = useState<string | null>(null)

  useEffect(() => {
    const timeout = setTimeout(() => {
      setDebouncedQuery(query)
      setPage(1)
    }, 350)
    return () => clearTimeout(timeout)
  }, [query])

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      const data = await getCustomChecks(pluginId, { page, per_page: PER_PAGE, search: debouncedQuery })
      setItems(data.items)
      setMeta({ pages: data.pages, total: data.total, hasNext: data.has_next, hasPrev: data.has_prev })
    } catch (err) {
      setLoadError(errorMessage(err, 'Unable to load the custom checks.'))
    } finally {
      setIsLoading(false)
    }
  }, [pluginId, page, debouncedQuery])

  useEffect(() => {
    void load()
  }, [load])

  const save = async (input: CustomCheckInput) => {
    setIsSaving(true)
    setDialogError(null)
    try {
      if (dialog === 'add') await addCustomCheck(pluginId, input)
      else if (dialog) await changeCustomCheck(pluginId, dialog.id, input)
      setDialog(null)
      await load()
      await onChanged()
    } catch (err) {
      setDialogError(errorMessage(err, 'Unable to save the check.'))
    } finally {
      setIsSaving(false)
    }
  }

  const act = async (check: CustomCheckItem, action: 'pause' | 'resume' | 'remove') => {
    if (action === 'remove' && !window.confirm(`Remove ${check.name} from ${check.device.hostname}?`)) return
    setBusyId(check.id)
    setActionError(null)
    try {
      if (action === 'pause') await pauseCustomCheck(pluginId, check.id)
      else if (action === 'resume') await resumeCustomCheck(pluginId, check.id)
      else await removeCustomCheck(pluginId, check.id)
      await load()
      await onChanged()
    } catch (err) {
      setActionError(errorMessage(err, 'Unable to change the check.'))
    } finally {
      setBusyId(null)
    }
  }

  const buttonClass =
    'flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1 text-xs font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10'

  return (
    <section>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Custom checks</h4>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-2 py-1 dark:border-white/10 dark:bg-[#0D1117]">
            <Search className="h-3.5 w-3.5 text-gray-500" />
            <input
              type="search"
              aria-label="Search custom checks"
              placeholder="Search name, device or IP"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-40 bg-transparent text-xs text-gray-900 outline-none placeholder:text-gray-500 dark:text-white"
            />
          </div>
          <button
            type="button"
            onClick={() => {
              setDialogError(null)
              setDialog('add')
            }}
            className="flex items-center gap-1 rounded-lg bg-[#ffb100] px-3 py-1 text-xs font-semibold text-black hover:brightness-105"
          >
            <Plus className="h-3.5 w-3.5" /> Add check
          </button>
        </div>
      </div>

      {loadError && (
        <p className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-300">{loadError}</p>
      )}
      {actionError && (
        <p role="alert" className="mb-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-300">
          {actionError}
        </p>
      )}

      {isLoading ? (
        <div className="flex items-center py-6 text-sm text-gray-500 dark:text-gray-400">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading checks…
        </div>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-gray-300 px-3 py-4 text-sm text-gray-500 dark:border-white/15 dark:text-gray-400">
          {debouncedQuery
            ? 'No custom checks match your search.'
            : 'No checks yet. Add one to run this plugin against a device.'}
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((check) => {
            const busy = busyId === check.id
            return (
              <div key={check.id} className="rounded-xl border border-gray-200 p-3 dark:border-white/10">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="break-words text-sm font-medium text-gray-900 dark:text-white">{check.name}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {check.device.hostname} · {check.device.ip_address}
                    </p>
                  </div>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[check.status.kind]}`}>
                    {STATUS_LABELS[check.status.kind]}
                  </span>
                </div>

                {summarize(check, fields) && (
                  <p className="mt-1.5 break-all font-mono text-xs text-gray-600 dark:text-gray-300">{summarize(check, fields)}</p>
                )}
                <p className="mt-1 break-words text-xs text-gray-600 dark:text-gray-300">{check.status.output}</p>

                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <span>{check.paused ? 'Paused' : `Running since ${formatDateTime(check.running_since)}`}</span>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => {
                        setDialogError(null)
                        setDialog(check)
                      }}
                      aria-label={`Change ${check.name} on ${check.device.hostname}`}
                      className={buttonClass}
                    >
                      <Pencil className="h-3 w-3" /> Change
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => act(check, check.paused ? 'resume' : 'pause')}
                      aria-label={`${check.paused ? 'Resume' : 'Pause'} ${check.name} on ${check.device.hostname}`}
                      className={buttonClass}
                    >
                      {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : check.paused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
                      {check.paused ? 'Resume' : 'Pause'}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => act(check, 'remove')}
                      aria-label={`Remove ${check.name} from ${check.device.hostname}`}
                      className={buttonClass}
                    >
                      <Trash2 className="h-3 w-3" /> Remove
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>
          Page {page} of {meta.pages} · {meta.total} {meta.total === 1 ? 'check' : 'checks'}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setPage(page - 1)}
            disabled={!meta.hasPrev}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10"
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setPage(page + 1)}
            disabled={!meta.hasNext}
            className="rounded-lg px-3 py-1 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-white/10"
          >
            Next
          </button>
        </div>
      </div>

      {dialog && (
        <CustomCheckDialog
          pluginName={pluginName}
          fields={fields}
          check={dialog === 'add' ? null : dialog}
          isSaving={isSaving}
          error={dialogError}
          onCancel={() => setDialog(null)}
          onSave={save}
        />
      )}
    </section>
  )
}
