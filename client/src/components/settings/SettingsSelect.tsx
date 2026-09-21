interface SettingsSelectOption { value: string; label: string }
interface SettingsSelectProps {
  label: string; value: string; options: SettingsSelectOption[]
  onChange: (value: string) => void; description?: string
}

export function SettingsSelect({ label, value, options, onChange, description }: SettingsSelectProps) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium text-[var(--text)]">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--text)] outline-none transition duration-200 focus:border-[#ffb100]"
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} className="bg-[var(--card)] text-[var(--text)]">{opt.label}</option>
        ))}
      </select>
      {description && <p className="mt-1.5 text-xs text-[var(--text-muted)]">{description}</p>}
    </div>
  )
}
