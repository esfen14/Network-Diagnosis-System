export const FIVE_MINUTES_HOURS = 5 / 60

export type TrendHours = number

export const TREND_HOURS_OPTIONS: { value: TrendHours; label: string }[] = [
  { value: FIVE_MINUTES_HOURS, label: 'Last 5 minutes' },
  { value: 1, label: 'Last hour' },
  { value: 6, label: 'Last 6 hours' },
  { value: 24, label: 'Last 24 hours' },
  { value: 168, label: 'Last 7 days' },
]

export function trendBuckets(hours: TrendHours) {
  return hours < 1 ? 5 : 24
}
