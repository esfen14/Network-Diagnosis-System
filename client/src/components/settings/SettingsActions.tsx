import { useEffect, useState } from 'react'
import { Check, Loader2, RotateCcw } from 'lucide-react'

interface SettingsActionsProps {
  hasChanges: boolean
  onSave: () => void | Promise<void>
  onDiscard: () => void
  onReset?: () => void
  isSaving?: boolean
  saveError?: string | null
}

export function SettingsActions({
  hasChanges,
  onSave,
  onDiscard,
  onReset,
  isSaving = false,
  saveError = null,
}: SettingsActionsProps) {
  const [justSaved, setJustSaved] = useState(false)

  // Flip a brief "Saved" confirmation once a save completes successfully
  // (isSaving goes true -> false with no error) — the button disabling
  // itself was the only feedback before, which read as "did nothing".
  const [wasSaving, setWasSaving] = useState(false)
  useEffect(() => {
    if (isSaving) {
      setWasSaving(true)
      setJustSaved(false)
    } else if (wasSaving) {
      setWasSaving(false)
      if (!saveError) {
        setJustSaved(true)
        const id = setTimeout(() => setJustSaved(false), 2000)
        return () => clearTimeout(id)
      }
    }
  }, [isSaving, saveError, wasSaving])

  return (
    <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--border)] pt-6">
      <div className="flex items-center gap-3">
        {onReset && (
          <button type="button" onClick={onReset} className="text-sm text-[var(--text-muted)] transition hover:text-[var(--text)]">
            Reset to Defaults
          </button>
        )}
        {saveError && (
          <span className="text-sm text-red-500">{saveError}</span>
        )}
        {justSaved && !saveError && (
          <span className="flex items-center gap-1.5 text-sm text-emerald-500">
            <Check size={15} /> Saved
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button type="button" disabled={!hasChanges || isSaving} onClick={onDiscard}
          className="flex items-center gap-2 rounded-xl border border-[var(--border)] px-4 py-2.5 text-sm text-[var(--text-muted)] transition hover:bg-[var(--hover)] disabled:cursor-not-allowed disabled:opacity-40">
          <RotateCcw size={15} /> Discard Changes
        </button>
        <button type="button" disabled={!hasChanges || isSaving} onClick={onSave}
          className="flex min-w-[140px] items-center justify-center gap-2 rounded-xl bg-[#ffb100] px-4 py-2.5 text-sm font-medium text-black transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40">
          {isSaving ? (
            <>
              <Loader2 size={15} className="animate-spin" /> Saving...
            </>
          ) : (
            <>
              <Check size={15} /> Save Changes
            </>
          )}
        </button>
      </div>
    </div>
  )
}
