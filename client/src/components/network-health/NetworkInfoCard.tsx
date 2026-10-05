import { Calendar, Clock, Pencil } from 'lucide-react'
import { useState } from 'react'
import { errorMessage } from '../../lib/api'
import { DEFAULT_NETWORK_NAME, type NetworkProfile } from '../../hooks/useNetworkProfile'

const PLACEHOLDERS: Record<string, string> = {
  'IP Range': 'e.g. 192.168.1.1 - 192.168.1.254',
  'Gateway Device': 'e.g. R1 - 192.168.1.1',
  'Subnet Mask': 'e.g. 255.255.255.0',
  'DNS Server': 'e.g. 192.168.0.5',
  ISP: 'e.g. your internet provider',
  Location: 'e.g. building and floor',
}

const FALLBACK_PROFILE: NetworkProfile = {
  name: DEFAULT_NETWORK_NAME,
  reference: '',
  details: Object.keys(PLACEHOLDERS).map((label) => ({ label, value: '' })),
}

type NetworkInfoCardProps = {
  lastScanDate: string
  lastScanTime: string
  profile: NetworkProfile | null
  onSave?: (profile: NetworkProfile) => Promise<void>
}

const inputClass =
  'w-full rounded-lg border border-white/40 bg-white/20 px-2 py-1 text-sm text-white placeholder-white/60 outline-none focus:border-white'

export function NetworkInfoCard({ lastScanDate, lastScanTime, profile, onSave }: NetworkInfoCardProps) {
  const current = profile ?? FALLBACK_PROFILE
  const [draft, setDraft] = useState<NetworkProfile | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const editing = draft !== null
  const shown = draft ?? current

  const startEdit = () => {
    setError(null)
    setDraft({ ...current, details: current.details.map((d) => ({ ...d })) })
  }

  const handleSave = async () => {
    if (!draft || !onSave) return
    if (!draft.name.trim()) {
      setError('Network name is required.')
      return
    }
    setIsSaving(true)
    setError(null)
    try {
      await onSave(draft)
      setDraft(null)
    } catch (err) {
      setError(errorMessage(err, 'Could not save the network profile.'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div
      className="flex min-h-[400px] flex-col justify-between rounded-[32px] p-8 shadow-xl"
      style={{ background: 'linear-gradient(180deg, #F5A317 25%, #F8BB54 100%)' }}
    >
      <div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            {editing ? (
              <div className="space-y-2">
                <input
                  aria-label="Network name"
                  maxLength={100}
                  value={shown.name}
                  onChange={(e) => setDraft({ ...shown, name: e.target.value })}
                  className={`${inputClass} text-lg font-semibold`}
                />
                <input
                  aria-label="Reference"
                  maxLength={50}
                  value={shown.reference}
                  onChange={(e) => setDraft({ ...shown, reference: e.target.value })}
                  placeholder="Reference tag (optional)"
                  className={inputClass}
                />
              </div>
            ) : (
              <>
                <h2 className="text-2xl font-semibold text-white">{shown.name}</h2>
                {shown.reference && <p className="text-sm text-white/80">{shown.reference}</p>}
              </>
            )}
          </div>
          <div className="text-right">
            <p className="text-sm font-semibold text-white">Last Scan</p>
            <div className="mt-1 flex items-center justify-end gap-3 text-sm text-white/80">
              <span className="flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5" />
                {lastScanDate}
              </span>
              <span className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                {lastScanTime}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {shown.details.map(({ label, value }, index) => (
            <div key={label}>
              <p className="text-sm font-semibold text-white">{label}</p>
              {editing ? (
                <input
                  aria-label={label}
                  placeholder={PLACEHOLDERS[label]}
                  maxLength={100}
                  value={value}
                  onChange={(e) => {
                    const details = shown.details.map((d, i) => (i === index ? { ...d, value: e.target.value } : d))
                    setDraft({ ...shown, details })
                  }}
                  className={inputClass}
                />
              ) : (
                <p className="text-sm text-white/80">{value || 'Not set'}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="pt-8">
        {error && (
          <p role="alert" className="mb-2 text-sm font-medium text-white">
            {error}
          </p>
        )}
        {editing ? (
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setDraft(null)}
              disabled={isSaving}
              className="flex-1 rounded-full border border-white/60 px-6 py-3.5 text-sm font-semibold text-white transition hover:bg-white/10 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isSaving}
              className="flex-1 rounded-full bg-[#0D1117] px-6 py-3.5 text-sm font-semibold text-white shadow-md transition hover:bg-black/90 disabled:opacity-50"
            >
              {isSaving ? 'Saving…' : 'Save'}
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={startEdit}
            disabled={!onSave}
            title={onSave ? undefined : "Editing needs the Network Discovery settings permission"}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-[#0D1117] px-6 py-3.5 text-sm font-semibold text-white shadow-md transition hover:bg-black/90 active:scale-[0.99] cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Pencil className="h-4 w-4" />
            Edit
          </button>
        )}
      </div>
    </div>
  )
}
