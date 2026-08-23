interface SettingsSelectOption {
  value: string
  label: string
}

interface SettingsSelectProps {
  label: string
  value: string
  options: SettingsSelectOption[]
  onChange: (value: string) => void
  description?: string
}

export function SettingsSelect({
  label,
  value,
  options,
  onChange,
  description,
}: SettingsSelectProps) {
  return (
    <div>
      <label className="mb-2 block text-sm font-medium text-gray-200">
        {label}
      </label>

      <select
        value={value}
        onChange={(event) =>
          onChange(event.target.value)
        }
        className="
          h-10
          w-full
          rounded-xl
          border
          border-var(--system-border)
          bg-var(--system-card-secondary)
          px-3
          text-sm
          text-var(--system-text)
          outline-none
          transition
          duration-200
          focus:border-pinpoint-orange
          focus:ring-1
          focus:ring-pinpoint-orange
        "
      >
        {options.map((option) => (
          <option
            key={option.value}
            value={option.value}
          >
            {option.label}
          </option>
        ))}
      </select>

      {description && (
        <p className="mt-1.5 text-xs text-gray-500">
          {description}
        </p>
      )}
    </div>
  )
}