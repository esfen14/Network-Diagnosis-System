// X-axis label for a trends bucket: weekday + hour for the 7-day window,
// otherwise just the time. Shared by the Network Health trend charts.
export function formatBucketLabel(iso: string, hours: number) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  if (hours === 168) return d.toLocaleDateString(undefined, { weekday: 'short', hour: '2-digit' })
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}
