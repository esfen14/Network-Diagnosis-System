import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { errorMessage } from '../../lib/api'
import { searchCustomCheckDevices } from '../../lib/pluginApi'
import type { CustomCheckDevice, CustomCheckField, CustomCheckInput, CustomCheckItem } from '../../types/plugin'

type Props = {
  pluginName: string
  fields: CustomCheckField[]
  // The check being changed; null when adding one. The device of an existing check cannot change.
  check: CustomCheckItem | null
  isSaving: boolean
  // The server's message when it refused the request.
  error: string | null
  onCancel: () => void
  onSave: (input: CustomCheckInput) => void
}

// Arguments the server refuses outright (they would end a quoted shell argument or expand a macro).
const FORBIDDEN = /['"`!$;\\\n\r]/

// check_by_ssh runs whatever command it is given on the device, so it carries a warning.
const RUNS_COMMANDS = ['check_by_ssh']

export function CustomCheckDialog({ pluginName, fields, check, isSaving, error, onCancel, onSave }: Props) {
  const [name, setName] = useState(check?.name ?? '')
  const [values, setValues] = useState<Record<string, string>>(check?.variables ?? {})
  const [deviceQuery, setDeviceQuery] = useState('')
  const [devices, setDevices] = useState<CustomCheckDevice[]>([])
  const [device, setDevice] = useState<CustomCheckDevice | null>(null)
  const [deviceError, setDeviceError] = useState<string | null>(null)

  useEffect(() => {
    if (check) return
    let cancelled = false
    const timeout = setTimeout(async () => {
      try {
        const found = await searchCustomCheckDevices(deviceQuery)
        if (!cancelled) {
          setDevices(found)
          setDeviceError(null)
        }
      } catch (err) {
        if (!cancelled) setDeviceError(errorMessage(err, 'Unable to load devices.'))
      }
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(timeout)
    }
  }, [deviceQuery, check])

  const problems: string[] = []
  if (!check && !device) problems.push('Choose a device.')
  if (!name.trim()) problems.push('Enter a name.')
  for (const field of fields) {
    const value = (values[field.name] ?? '').trim()
    if (field.required && !value) problems.push(`${field.label} is required.`)
    if (FORBIDDEN.test(value)) problems.push(`${field.label} contains a character that is not allowed.`)
  }

  const submit = () => {
    if (problems.length > 0) return
    const variables: Record<string, string> = {}
    for (const field of fields) {
      const value = (values[field.name] ?? '').trim()
      if (value) variables[field.name] = value
    }
    onSave({ ...(check ? {} : { device_id: device!.id }), name: name.trim(), variables })
  }

  const title = check ? `Change ${check.name}` : `Add a ${pluginName} check`

  return (
    <div role="dialog" aria-modal="true" aria-label={title} className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
      <div className="max-h-full w-full max-w-md space-y-3 overflow-y-auto rounded-2xl border border-gray-200 bg-white p-5 shadow-xl dark:border-white/10 dark:bg-[#171B20]">
        <h3 className="text-base font-semibold text-gray-900 dark:text-white">{title}</h3>

        {RUNS_COMMANDS.includes(pluginName) && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
            This runs the command you enter on the device over SSH. Use a command you trust, and a key file that already
            exists on the Nagios server; passwords are not stored.
          </p>
        )}

        <div>
          <label htmlFor="custom-check-name" className="mb-1 block text-xs text-gray-500 dark:text-gray-400">
            Name
          </label>
          <input
            id="custom-check-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={60}
            autoFocus
            className="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-900 outline-none focus:border-[#ffb100] dark:border-white/15 dark:bg-[#0D1117] dark:text-white"
          />
        </div>

        {check ? (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Device: {check.device.hostname} · {check.device.ip_address}. To check another device, remove this check and add
            a new one.
          </p>
        ) : (
          <div>
            <label htmlFor="custom-check-device" className="mb-1 block text-xs text-gray-500 dark:text-gray-400">
              Device
            </label>
            <input
              id="custom-check-device"
              type="search"
              placeholder="Search by name or IP"
              value={deviceQuery}
              onChange={(e) => {
                setDeviceQuery(e.target.value)
                setDevice(null)
              }}
              className="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-900 outline-none focus:border-[#ffb100] dark:border-white/15 dark:bg-[#0D1117] dark:text-white"
            />
            {deviceError && <p className="mt-1 text-xs text-red-600 dark:text-red-300">{deviceError}</p>}
            <ul aria-label="Devices" className="mt-1 max-h-32 overflow-y-auto rounded-lg border border-gray-200 dark:border-white/10">
              {devices.length === 0 && !deviceError && (
                <li className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">No devices match.</li>
              )}
              {devices.map((candidate) => (
                <li key={candidate.id}>
                  <button
                    type="button"
                    onClick={() => setDevice(candidate)}
                    aria-pressed={device?.id === candidate.id}
                    className={`block w-full px-3 py-1.5 text-left text-xs hover:bg-gray-100 dark:hover:bg-white/10 ${
                      device?.id === candidate.id ? 'bg-[#ffb100]/20 font-semibold' : ''
                    } text-gray-800 dark:text-gray-200`}
                  >
                    {candidate.hostname} · {candidate.ip_address}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {fields.map((field) => (
          <div key={field.name}>
            <label htmlFor={`custom-check-${field.name}`} className="mb-1 block text-xs text-gray-500 dark:text-gray-400">
              {field.label}
              {field.required ? ' *' : ''} <span className="font-mono text-gray-400">{field.flag}</span>
            </label>
            <input
              id={`custom-check-${field.name}`}
              value={values[field.name] ?? ''}
              placeholder={field.placeholder}
              onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
              className="w-full rounded-lg border border-gray-300 bg-gray-50 px-3 py-2 font-mono text-sm text-gray-900 outline-none focus:border-[#ffb100] dark:border-white/15 dark:bg-[#0D1117] dark:text-white"
            />
          </div>
        ))}

        {error && (
          <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-300">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSaving}
            className="rounded-lg px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-50 dark:text-gray-300 dark:hover:bg-white/10"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={isSaving || problems.length > 0}
            title={problems[0]}
            className="flex items-center gap-2 rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-black hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
            {check ? 'Save changes' : 'Add check'}
          </button>
        </div>
      </div>
    </div>
  )
}
