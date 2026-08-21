interface SettingsToggleProps {
  label: string
  description?: string
  enabled: boolean
  onChange: (enabled: boolean) => void
}

export function SettingsToggle({
  label,
  description,
  enabled,
  onChange,
}: SettingsToggleProps) {
  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-[var(--system-text)]">
            {label}
          </p>

          {description && (
            <p className="mt-1 text-xs text-[var(--system-text-secondary)]">
              {description}
            </p>
          )}
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => onChange(!enabled)}
          className={`
            relative
            h-6
            w-11
            shrink-0
            rounded-full
            border
            transition-colors
            duration-200
            focus:outline-none
            focus:ring-2
            focus:ring-orange-400/40
            ${
              enabled
                ? 'border-orange-500 bg-orange-500'
                : 'border-gray-400 bg-gray-300 dark:border-gray-600 dark:bg-gray-700'
            }
          `}
        >
          <span
            className={`
              absolute
              top-0.5
              h-5
              w-5
              rounded-full
              bg-white
              shadow-md
              transition-all
              duration-200
              ${
                enabled
                  ? 'left-[22px]'
                  : 'left-0.5'
              }
            `}
          />
        </button>
      </div>
    </div>
  )
}