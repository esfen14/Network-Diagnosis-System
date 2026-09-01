import { useState } from 'react'
import { Download } from 'lucide-react'
import type { ExportFormat } from '../../types/settings'

type ExportMenuProps = {
  allowedFormats: ExportFormat[]
  onExport: (format: ExportFormat) => void
  className?: string
  buttonClassName?: string
  label?: boolean
}

// Restricts the offered export formats to the system-wide "Export Formats"
// setting — an admin who disables XLS, for example, should never see it
// offered here.
export function ExportMenu({
  allowedFormats,
  onExport,
  className = '',
  buttonClassName = 'rounded-lg p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-white/10 dark:hover:text-white',
  label = false,
}: ExportMenuProps) {
  const [open, setOpen] = useState(false)

  if (allowedFormats.length === 0) {
    return null
  }

  return (
    <div className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`flex items-center justify-center gap-2 ${buttonClassName}`}
      >
        <Download className="h-4 w-4" />
        {label && 'Export'}
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full z-20 mt-2 w-32 rounded-xl border border-gray-200 bg-white p-1 shadow-lg dark:border-white/10 dark:bg-[#171B20]">
            {allowedFormats.map((format) => (
              <button
                key={format}
                type="button"
                onClick={() => {
                  onExport(format)
                  setOpen(false)
                }}
                className="block w-full rounded-lg px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/10"
              >
                {format}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
