import type { DateTimeFormat } from '../types/settings'

function pad(n: number) {
  return String(n).padStart(2, '0')
}

/** Parses "UTC+08:00" / "UTC-05:00" into a minute offset (e.g. 480 / -300). */
function parseUtcOffsetMinutes(timeZone: string): number {
  const match = /^UTC([+-])(\d{2}):(\d{2})$/.exec(timeZone)
  if (!match) return 0

  const sign = match[1] === '-' ? -1 : 1
  const hours = Number(match[2])
  const minutes = Number(match[3])
  return sign * (hours * 60 + minutes)
}

// Shifts the Date's absolute instant by the configured UTC offset, then
// reads it back with the UTC getters below — this makes display depend
// only on the app's Time Zone setting, never on the viewer's own machine
// clock/timezone.
function toZoned(date: Date, timeZone: string): Date {
  const offsetMinutes = parseUtcOffsetMinutes(timeZone)
  return new Date(date.getTime() + offsetMinutes * 60 * 1000)
}

/** Formats just the date portion, in the given time zone, per the dateTimeFormat preference. */
export function formatDate(
  date: Date,
  format: DateTimeFormat,
  timeZone = 'UTC+00:00'
): string {
  const zoned = toZoned(date, timeZone)
  const dd = pad(zoned.getUTCDate())
  const mm = pad(zoned.getUTCMonth() + 1)
  const yyyy = zoned.getUTCFullYear()

  switch (format) {
    case 'MM/DD/YYYY':
      return `${mm}/${dd}/${yyyy}`
    case 'YYYY-MM-DD':
      return `${yyyy}-${mm}-${dd}`
    case 'DD/MM/YYYY':
    default:
      return `${dd}/${mm}/${yyyy}`
  }
}

/** Formats a time as e.g. "02:52 PM", in the given time zone. */
export function formatTime(date: Date, timeZone = 'UTC+00:00'): string {
  const zoned = toZoned(date, timeZone)
  let hours = zoned.getUTCHours()
  const minutes = pad(zoned.getUTCMinutes())
  const period = hours >= 12 ? 'PM' : 'AM'
  hours = hours % 12 || 12
  return `${pad(hours)}:${minutes} ${period}`
}

/** Formats a date + time, in the given time zone, per the dateTimeFormat preference. */
export function formatDateTime(
  date: Date,
  format: DateTimeFormat,
  timeZone = 'UTC+00:00'
): string {
  return `${formatDate(date, format, timeZone)} ${formatTime(date, timeZone)}`
}

/**
 * Parses the loose date strings used by mock data (e.g. "2026-01-20 10:45 AM",
 * "Oct 21, 2025 - 14:32", "2026-07-26 09:15:42") into a Date. Falls back to
 * the current time if the string can't be parsed, so display never breaks.
 */
export function parseMockDate(value: string): Date {
  const normalized = value.replace(' - ', ' ')
  const parsed = new Date(normalized)
  return isNaN(parsed.getTime()) ? new Date() : parsed
}
