import { useState } from 'react'
import { CheckCircle2, History, Upload, XCircle } from 'lucide-react'
import { rollbackPluginUpdate, updatePlugin } from '../../lib/pluginApi'
import { errorMessage } from '../../lib/api'
import { FAILED_STATUSES } from '../../types/plugin'
import type { PluginDetails, PluginUpdateResult } from '../../types/plugin'

type Props = {
  details: PluginDetails
  onChanged: () => Promise<void> | void
}

type SourceMode = 'file' | 'url'

const ACCEPTED_ARCHIVES = '.tar.gz,.tgz,.zip'

export function PluginUpdateSection({ details, onChanged }: Props) {
  const [mode, setMode] = useState<SourceMode>('file')
  const [file, setFile] = useState<File | null>(null)
  const [url, setUrl] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<PluginUpdateResult | null>(null)
  const [rollbackMessage, setRollbackMessage] = useState<string | null>(null)

  // The backend refuses updates while the plugin is failed or awaiting rollback.
  const isBlocked = FAILED_STATUSES.includes(details.status) || details.status === 'Rollback'
  const hasSource = mode === 'file' ? file !== null : url.trim() !== ''

  const handleUpdate = async () => {
    setIsBusy(true)
    setError(null)
    setResult(null)
    setRollbackMessage(null)
    try {
      const source = mode === 'file' && file ? { file } : { url: url.trim() }
      setResult(await updatePlugin(details.id, source))
      setFile(null)
      setUrl('')
      await onChanged()
    } catch (err) {
      setError(errorMessage(err, 'Update failed.'))
    } finally {
      setIsBusy(false)
    }
  }

  const handleRollback = async () => {
    if (!window.confirm(`Restore the previous version of ${details.display_name || details.name}?`)) return
    setIsBusy(true)
    setError(null)
    setResult(null)
    try {
      const rollback = await rollbackPluginUpdate(details.id)
      setRollbackMessage(
        rollback.restored_version
          ? `Restored version ${rollback.restored_version}.`
          : 'Previous version restored.'
      )
      await onChanged()
    } catch (err) {
      setError(errorMessage(err, 'Rollback failed.'))
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <section>
      <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-white">Update</h4>

      <div className="space-y-3 rounded-xl border border-gray-200 p-3 dark:border-white/10">
        {details.status === 'Rollback' && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
            The last update failed. Roll back to restore the previous version before updating again.
          </p>
        )}

        {isBlocked && details.status !== 'Rollback' && (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Updates are unavailable while the plugin is in the “{details.status}” state.
          </p>
        )}

        {!isBlocked && (
          <>
            <div className="flex gap-1 rounded-lg bg-gray-100 p-1 text-xs dark:bg-white/5">
              {(['file', 'url'] as SourceMode[]).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setMode(option)}
                  className={`flex-1 rounded-md px-3 py-1 font-medium ${
                    mode === option
                      ? 'bg-white text-gray-900 shadow-sm dark:bg-[#0D1117] dark:text-white'
                      : 'text-gray-500 dark:text-gray-400'
                  }`}
                >
                  {option === 'file' ? 'Upload archive' : 'From URL'}
                </button>
              ))}
            </div>

            {mode === 'file' ? (
              <label className="block text-xs text-gray-500 dark:text-gray-400">
                Archive (.tar.gz, .tgz or .zip) containing a file named{' '}
                <span className="font-mono">{details.name}</span>
                <input
                  type="file"
                  accept={ACCEPTED_ARCHIVES}
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="mt-1 block w-full text-xs text-gray-700 file:mr-3 file:rounded-lg file:border-0 file:bg-gray-100 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-gray-700 dark:text-gray-300 dark:file:bg-white/10 dark:file:text-gray-200"
                />
              </label>
            ) : (
              <label className="block text-xs text-gray-500 dark:text-gray-400">
                Archive URL
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/plugin-1.2.3.tar.gz"
                  className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs text-gray-900 outline-none focus:border-gray-500 dark:border-white/20 dark:bg-[#0D1117] dark:text-white"
                />
              </label>
            )}
          </>
        )}

        <div className="flex flex-wrap gap-2">
          {!isBlocked && (
            <button
              type="button"
              onClick={handleUpdate}
              disabled={isBusy || !hasSource}
              className="flex items-center gap-2 rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Upload className="h-4 w-4" /> {isBusy ? 'Working…' : 'Update Plugin'}
            </button>
          )}
          <button
            type="button"
            onClick={handleRollback}
            disabled={isBusy || !details.rollback_available}
            title={details.rollback_available ? undefined : 'No backup of a previous version is available.'}
            className="flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
          >
            <History className="h-4 w-4" /> Roll Back
          </button>
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-300">
            {error}
          </p>
        )}

        {rollbackMessage && (
          <p className="flex items-center gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300">
            <CheckCircle2 className="h-4 w-4" /> {rollbackMessage}
          </p>
        )}

        {result && (
          <div
            className={`space-y-1 rounded-lg px-3 py-2 text-xs ${
              result.success
                ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300'
                : 'bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300'
            }`}
          >
            <div className="flex items-center gap-2 font-medium">
              {result.success ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
              {result.success
                ? `Updated ${result.previous_version ?? 'unknown'} → ${result.current_version ?? 'unknown'}.`
                : `Update failed at ${result.failed_step ?? 'an unknown step'}. The previous version is backed up — use Roll Back to restore it.`}
            </div>
            {!result.success && result.nagios_check && !result.nagios_check.passed && (
              <pre className="max-h-32 overflow-auto whitespace-pre-wrap font-mono opacity-90">
                {result.nagios_check.output}
              </pre>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
