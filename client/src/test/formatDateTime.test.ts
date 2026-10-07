import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  BROWSER_TIME_ZONE,
  formatDateTime,
  formatServerDateTime,
  formatWeekday,
  parseServerDate,
} from '../utils/formatDateTime'
import { formatBucketLabel } from '../utils/formatBucketLabel'

const INSTANT = new Date('2026-10-07T08:30:00Z')

describe('parseServerDate', () => {
  it('reads a timestamp with no offset as UTC, not local time', () => {
    expect(parseServerDate('2026-10-07T08:30:00')?.toISOString()).toBe('2026-10-07T08:30:00.000Z')
    expect(parseServerDate('2026-10-07 08:30:00')?.toISOString()).toBe('2026-10-07T08:30:00.000Z')
  })

  it('keeps an explicit offset', () => {
    expect(parseServerDate('2026-10-07T16:30:00+08:00')?.toISOString()).toBe('2026-10-07T08:30:00.000Z')
    expect(parseServerDate('2026-10-07T08:30:00Z')?.toISOString()).toBe('2026-10-07T08:30:00.000Z')
  })

  it('returns null for missing or invalid values', () => {
    expect(parseServerDate(null)).toBeNull()
    expect(parseServerDate('')).toBeNull()
    expect(parseServerDate('not a date')).toBeNull()
  })
})

describe('time zone setting', () => {
  afterEach(() => vi.restoreAllMocks())

  it('applies a fixed UTC offset', () => {
    expect(formatDateTime(INSTANT, 'DD/MM/YYYY', 'UTC+08:00')).toBe('07/10/2026 04:30 PM')
    expect(formatDateTime(INSTANT, 'YYYY-MM-DD', 'UTC-05:00')).toBe('2026-10-07 03:30 AM')
  })

  it("follows the browser's own offset when set to Browser", () => {
    // getTimezoneOffset is minutes behind UTC: -480 means UTC+08:00.
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
    expect(formatDateTime(INSTANT, 'DD/MM/YYYY', BROWSER_TIME_ZONE)).toBe('07/10/2026 04:30 PM')
    vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(300)
    expect(formatDateTime(INSTANT, 'DD/MM/YYYY', BROWSER_TIME_ZONE)).toBe('07/10/2026 03:30 AM')
  })

  it('formats a server string and shows a dash when it is missing', () => {
    expect(formatServerDateTime('2026-10-07T08:30:00', 'DD/MM/YYYY', 'UTC+08:00')).toBe('07/10/2026 04:30 PM')
    expect(formatServerDateTime(null, 'DD/MM/YYYY', 'UTC+08:00')).toBe('—')
  })

  it('shows the weekday in the chosen zone', () => {
    const lateSunday = new Date('2026-10-04T20:00:00Z') // Sunday UTC, already Monday at UTC+08:00
    expect(formatWeekday(lateSunday, 'UTC+00:00')).toBe('Sun')
    expect(formatWeekday(lateSunday, 'UTC+08:00')).toBe('Mon')
  })

  it('labels chart buckets in the chosen zone', () => {
    expect(formatBucketLabel('2026-10-07T08:30:00+00:00', 24, 'UTC+08:00')).toBe('04:30 PM')
    expect(formatBucketLabel('2026-10-07T08:30:00+00:00', 168, 'UTC+08:00')).toBe('Wed 04:30 PM')
  })
})
