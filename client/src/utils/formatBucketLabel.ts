import { formatTime, formatWeekday } from './formatDateTime'

// X-axis label for a trends bucket: weekday + time for the 7-day window,
// otherwise just the time. Shared by the Network Health trend charts. Times
// follow the Time Zone setting (pass settings.timeZone).
export function formatBucketLabel(iso: string, hours: number, timeZone = 'UTC+00:00') {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const time = formatTime(d, timeZone)
  return hours === 168 ? `${formatWeekday(d, timeZone)} ${time}` : time
}
