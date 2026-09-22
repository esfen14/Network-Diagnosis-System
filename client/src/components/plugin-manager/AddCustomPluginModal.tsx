import { useRef, useState } from 'react'
import { CheckCircle2, Upload, X, XCircle } from 'lucide-react'
import { addCustomPlugin } from '../../lib/pluginApi'
import { errorMessage } from '../../lib/api'
import type { CustomPluginUploadResult } from '../../types/plugin'

type Props = {
  onClose: () => void
  onAdded: () => void
}

type Stage = 'form' | 'submitting' | 'result'

export function AddCustomPluginModal({ onClose, onAdded }: Props) {
  const [stage, setStage] = useState<Stage>('form')
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [result, setResult] = useState<CustomPluginUploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const handleSubmit = async () => {
    if (!file) return
    setStage('submitting')
    setError(null)
    try {
      const res = await addCustomPlugin(file, name.trim() || undefined)
      setResult(res)
      setStage('result')
      if (res.success) onAdded()
    } catch (err) {
      setError(errorMessage(err, 'Unable to add custom plugin.'))
      setStage('form')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl dark:bg-[#171B20]">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Add Custom Plugin
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Upload → Stage → Validate → Install → Register, run as one request.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {stage === 'form' && (
          <div className="mt-5 space-y-4">
            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
                {error}
              </div>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Plugin executable
              </label>
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="flex w-full items-center gap-3 rounded-xl border border-dashed border-gray-300 px-4 py-6 text-left text-sm text-gray-500 hover:border-gray-400 dark:border-white/20 dark:text-gray-400 dark:hover:border-white/40"
              >
                <Upload className="h-5 w-5 shrink-0" />
                {file ? file.name : 'Click to choose a file'}
              </button>
              <input
                ref={fileInput}
                type="file"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Display name (optional)
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. check_custom_service"
                className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-gray-500 dark:border-white/20 dark:bg-[#0D1117] dark:text-white"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!file}
                className="rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black disabled:cursor-not-allowed disabled:opacity-50"
              >
                Validate &amp; Register
              </button>
            </div>
          </div>
        )}

        {stage === 'submitting' && (
          <div className="mt-8 mb-4 flex flex-col items-center text-center">
            <div className="mb-4 h-12 w-12 animate-spin rounded-full border-4 border-amber-200 border-t-[#ffb100]" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Uploading, staging, and validating the plugin…
            </p>
          </div>
        )}

        {stage === 'result' && result && (
          <div className="mt-5 space-y-4">
            <div className="flex items-center gap-3">
              {result.success ? (
                <CheckCircle2 className="h-6 w-6 shrink-0 text-emerald-500" />
              ) : (
                <XCircle className="h-6 w-6 shrink-0 text-red-500" />
              )}
              <p className="text-sm font-medium text-gray-900 dark:text-white">
                {result.message}
              </p>
            </div>

            <ul className="space-y-1.5 rounded-xl border border-gray-200 p-3 dark:border-white/10">
              {result.checks.map((check) => (
                <li key={check.name} className="flex items-start gap-2 text-sm">
                  {check.passed ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                  ) : (
                    <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                  )}
                  <span className="text-gray-700 dark:text-gray-300">
                    <span className="font-medium">{check.name}</span> — {check.message}
                  </span>
                </li>
              ))}
            </ul>

            <div className="flex justify-end gap-2">
              {!result.success && (
                <button
                  type="button"
                  onClick={() => setStage('form')}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 dark:border-white/20 dark:text-gray-300 dark:hover:bg-white/10"
                >
                  Try Again
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black"
              >
                {result.success ? 'Done' : 'Close'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
