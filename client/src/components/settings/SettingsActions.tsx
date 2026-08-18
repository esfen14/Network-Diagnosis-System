import {
  Check,
  RotateCcw,
} from 'lucide-react'

interface SettingsActionsProps {
  hasChanges: boolean
  onSave: () => void
  onDiscard: () => void
  onReset?: () => void
}

export function SettingsActions({
  hasChanges,
  onSave,
  onDiscard,
  onReset,
}: SettingsActionsProps) {
  return (
    <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-[#2c323a] pt-6">

      <div>
        {onReset && (
          <button
            type="button"
            onClick={onReset}
            className="
              text-sm
              text-gray-500
              transition
              hover:text-gray-300
            "
          >
            Reset to Defaults
          </button>
        )}
      </div>

      <div className="flex items-center gap-3">

        <button
          type="button"
          disabled={!hasChanges}
          onClick={onDiscard}
          className="
            flex
            items-center
            gap-2
            rounded-xl
            border
            border-gray-600
            px-4
            py-2.5
            text-sm
            text-gray-300
            transition
            hover:bg-[#222831]
            disabled:cursor-not-allowed
            disabled:opacity-40
          "
        >
          <RotateCcw size={15} />

          Discard Changes
        </button>

        <button
          type="button"
          disabled={!hasChanges}
          onClick={onSave}
          className="
            flex
            items-center
            gap-2
            rounded-xl
            bg-pinpoint-orange
            px-4
            py-2.5
            text-sm
            font-medium
            text-white
            transition
            hover:opacity-90
            disabled:cursor-not-allowed
            disabled:opacity-40
          "
        >
          <Check size={15} />

          Save Changes
        </button>

      </div>
    </div>
  )
}