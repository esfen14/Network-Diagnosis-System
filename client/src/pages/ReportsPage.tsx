import { useEffect, useState } from 'react'
import { Activity, CheckCircle2, XCircle, Loader2 } from 'lucide-react'

import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { HostAvailabilityReportTable } from '../components/reports/HostAvailabilityReportTable'
import { NetworkServicesReportTable } from '../components/reports/NetworkServicesReportTable'
import { apiGet, errorMessage } from '../lib/api'
import {
  fromHostAvailabilityResponse,
  fromNetworkServicesResponse,
  type HostAvailabilityReport,
  type NetworkServicesReport,
  type ReportPeriod,
} from '../types/report'

type ReportView = 'availability' | 'network-services'

const PERIOD_OPTIONS: { value: ReportPeriod; label: string }[] = [
  { value: 'last_24h', label: 'Last 24 hours' },
  { value: 'today', label: 'Today' },
  { value: 'last_7d', label: 'Last 7 days' },
  { value: 'last_30d', label: 'Last 30 days' },
  { value: 'last_90d', label: 'Last 90 days' },
  { value: 'custom', label: 'Custom range' },
]

export function ReportsPage() {
  const [view, setView] = useState<ReportView>('availability')
  const [period, setPeriod] = useState<ReportPeriod>('last_24h')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')

  const [availability, setAvailability] = useState<HostAvailabilityReport | null>(null)
  const [networkServices, setNetworkServices] = useState<NetworkServicesReport | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function buildPeriodQuery() {
    const params = new URLSearchParams({ period })
    if (period === 'custom') {
      if (customStart) params.set('start', customStart)
      if (customEnd) params.set('end', customEnd)
    }
    return params.toString()
  }

  async function loadReport(showStatus = false) {
    if (period === 'custom' && (!customStart || !customEnd)) {
      setStatusMessage({ type: 'error', text: 'Pick a start and end date for a custom range.' })
      return
    }

    setIsLoading(true)
    setStatusMessage(null)
    try {
      const qs = buildPeriodQuery()
      if (view === 'availability') {
        const data = await apiGet<Parameters<typeof fromHostAvailabilityResponse>[0]>(
          `/api/system/report/availability?${qs}`
        )
        setAvailability(fromHostAvailabilityResponse(data))
      } else {
        const data = await apiGet<Parameters<typeof fromNetworkServicesResponse>[0]>(
          `/api/system/report/network-services?${qs}`
        )
        setNetworkServices(fromNetworkServicesResponse(data))
      }
      if (showStatus) setStatusMessage({ type: 'success', text: 'Report generated successfully.' })
    } catch (err) {
      setStatusMessage({ type: 'error', text: errorMessage(err, 'Could not run report. Please try again.') })
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadReport()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, period])

  return (
    <main className="ml-55 flex-1">
      <div className="space-y-6">

        <PageHeader
          title="Reports"
          highlight={view === 'availability' ? 'Host Availability' : 'Network Services'}
          description={
            view === 'availability'
              ? 'Host uptime and availability computed from live Nagios polling snapshots.'
              : 'Service health across every monitored host, aggregated by service name.'
          }
        />

        {/* Tabs */}
        <div className="flex gap-6 border-b border-gray-200 dark:border-white/10">
          <button type="button" onClick={() => setView('availability')}
            className={`pb-3 text-sm transition ${view === 'availability' ? 'border-b-2 border-gray-900 font-medium text-gray-900 dark:border-white dark:text-white' : 'text-gray-500 hover:text-gray-900 dark:text-white/60 dark:hover:text-white'}`}>
            Host Availability
          </button>
          <button type="button" onClick={() => setView('network-services')}
            className={`pb-3 text-sm transition ${view === 'network-services' ? 'border-b-2 border-gray-900 font-medium text-gray-900 dark:border-white dark:text-white' : 'text-gray-500 hover:text-gray-900 dark:text-white/60 dark:hover:text-white'}`}>
            Network Services
          </button>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 gap-5 md:grid-cols-4">
          {view === 'availability' ? (
            <>
              <SummaryStatCard
                title="Total Hosts"
                value={String(availability?.summary.total ?? 0)}
                subtitle="Reporting in this period"
                icon={Activity}
                gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
              />
              <SummaryStatCard
                title="Up"
                value={String(availability?.summary.up ?? 0)}
                subtitle="Currently reachable"
                icon={CheckCircle2}
                gradient="linear-gradient(135deg,#22C55E,#16A34A)"
              />
              <SummaryStatCard
                title="Down / Unreachable"
                value={String((availability?.summary.down ?? 0) + (availability?.summary.unreachable ?? 0))}
                subtitle="Needs attention"
                icon={XCircle}
                gradient="linear-gradient(135deg,#EF4444,#DC2626)"
              />
              <SummaryStatCard
                title="Uptime"
                value={availability?.summary.uptimePct != null ? `${availability.summary.uptimePct}%` : '—'}
                subtitle="Across all hosts"
                icon={Activity}
                gradient="linear-gradient(135deg,#6B7280,#4B5563)"
              />
            </>
          ) : (
            <>
              <SummaryStatCard
                title="Total Services"
                value={String(networkServices?.summary.totalServices ?? 0)}
                subtitle={`${networkServices?.summary.totalInstances ?? 0} instances`}
                icon={Activity}
                gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
              />
              <SummaryStatCard
                title="OK"
                value={String(networkServices?.summary.ok ?? 0)}
                subtitle="Healthy instances"
                icon={CheckCircle2}
                gradient="linear-gradient(135deg,#22C55E,#16A34A)"
              />
              <SummaryStatCard
                title="Warning / Critical"
                value={String((networkServices?.summary.warning ?? 0) + (networkServices?.summary.critical ?? 0))}
                subtitle="Needs attention"
                icon={XCircle}
                gradient="linear-gradient(135deg,#EF4444,#DC2626)"
              />
              <SummaryStatCard
                title="Uptime"
                value={networkServices?.summary.uptimePct != null ? `${networkServices.summary.uptimePct}%` : '—'}
                subtitle="Across all instances"
                icon={Activity}
                gradient="linear-gradient(135deg,#6B7280,#4B5563)"
              />
            </>
          )}
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as ReportPeriod)}
            className="h-10 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--text)] outline-none transition duration-200 focus:border-[#ffb100]"
          >
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value} className="bg-[var(--card)] text-[var(--text)]">{opt.label}</option>
            ))}
          </select>

          {period === 'custom' && (
            <>
              <input
                type="date"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
                className="h-10 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--text)] outline-none transition duration-200 focus:border-[#ffb100]"
              />
              <input
                type="date"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
                className="h-10 rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--text)] outline-none transition duration-200 focus:border-[#ffb100]"
              />
            </>
          )}

          <button
            type="button"
            onClick={() => loadReport(true)}
            disabled={isLoading}
            className="flex items-center gap-2 rounded-lg bg-white border border-gray-300 px-4 py-2 font-medium text-gray-800 shadow-sm transition hover:bg-gray-50 hover:shadow dark:bg-[#171B20] dark:border-white/10 dark:text-white dark:hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer"
          >
            {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
            {isLoading ? 'Running...' : 'Run Report'}
          </button>
        </div>

        {/* Status message */}
        {statusMessage && (
          <div
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm ${
              statusMessage.type === 'success'
                ? 'bg-green-50 text-green-700 border border-green-200'
                : 'bg-red-50 text-red-700 border border-red-200'
            }`}
          >
            {statusMessage.type === 'success' ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <XCircle className="h-4 w-4" />
            )}
            {statusMessage.text}
          </div>
        )}

        {view === 'availability' ? (
          <HostAvailabilityReportTable hosts={availability?.hosts ?? []} isLoading={isLoading} />
        ) : (
          <NetworkServicesReportTable services={networkServices?.services ?? []} isLoading={isLoading} />
        )}

      </div>
    </main>
  )
}
