import { useSystemSettings } from '../contexts/SystemSettingsContext'
import type { DateTimeFormat } from '../types/settings'
import { formatDate, formatServerDateTime, formatTime, parseServerDate } from '../utils/formatDateTime'

type ServerTime = string | number | Date | null | undefined

// Same defaults as DEFAULT_SYSTEM_SETTINGS, used when rendered outside SystemSettingsProvider.
const FALLBACK: { dateTimeFormat: DateTimeFormat; timeZone: string } = {
  dateTimeFormat: 'DD/MM/YYYY',
  timeZone: 'UTC+08:00',
}

function useSettingsOrDefaults() {
  try {
    // The hook's single useContext call always runs; it only throws when there is no provider.
    // eslint-disable-next-line react-hooks/rules-of-hooks
    const { settings, savedSettings } = useSystemSettings()
    return settings ?? savedSettings ?? FALLBACK
  } catch {
    return FALLBACK
  }
}

/**
 * Formatters that follow the Date format and Time Zone settings (the Time Zone
 * can be a fixed UTC offset or the viewer's browser). They accept server
 * timestamps as sent (ISO string, epoch ms or Date) and return "—" when the
 * value is missing. Works without the settings provider (defaults), so
 * components stay renderable on their own.
 */
export function useDisplayTime() {
  const { dateTimeFormat, timeZone } = useSettingsOrDefaults()

  return {
    dateTimeFormat,
    timeZone,
    formatDateTime: (value: ServerTime) => formatServerDateTime(value, dateTimeFormat, timeZone),
    formatDate: (value: ServerTime) => {
      const date = parseServerDate(value)
      return date ? formatDate(date, dateTimeFormat, timeZone) : '—'
    },
    formatTime: (value: ServerTime) => {
      const date = parseServerDate(value)
      return date ? formatTime(date, timeZone) : '—'
    },
  }
}
