import { useState } from 'react'
import { Activity, CheckCircle2, XCircle, Loader2 } from 'lucide-react'

import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { AllDevicesReportTable } from '../components/reports/AllDevicesReportTable'
import { LinkHealthReportTable } from '../components/reports/LinkHealthReportTable'
import { reports } from '../data/reports'

type ReportView = 'all-devices' | 'link-health'

export function ReportsPage() {
  const [view, setView] = useState<ReportView>('all-devices')
  const [selectedDate, setSelectedDate] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleRunReport = async () => {
    setIsRunning(true)
    setStatusMessage(null)
    try {
      // TODO: replace with real backend call, e.g.:
      // const res = await fetch(`/api/reports/run?view=${view}&date=${selectedDate}`, { method: 'POST' })
      // if (!res.ok) throw new Error('Failed to run report')
      await abang() // placeholder simulating backend latency
      setStatusMessage({ type: 'success', text: 'Report generated successfully.' })
    } catch (err) {
      setStatusMessage({ type: 'error', text: 'Could not run report. Please try again.' })
    } finally {
      setIsRunning(false)
    }
  }

  const handleExport = async () => {
    setIsExporting(true)
    setStatusMessage(null)
    try {
      // TODO: replace with real backend call, e.g.:
      // const res = await fetch(`/api/reports/export?view=${view}&date=${selectedDate}`)
      // const blob = await res.blob()
      // trigger file download from blob here
      await abang() // placeholder simulating backend latency
      setStatusMessage({ type: 'success', text: 'Export ready for download.' })
    } catch (err) {
      setStatusMessage({ type: 'error', text: 'Export failed. Please try again.' })
    } finally {
      setIsExporting(false)
    }
  }

  // Placeholder for the backend call 
  const abang = () => new Promise((resolve) => setTimeout(resolve, 900))

  return (
    <main className="ml-[220px] flex-1">
      <div className="space-y-6">

        <PageHeader
          title="Reports"
          highlight={view === 'all-devices' ? 'All Devices' : 'Link Health'}
          description={
            view === 'all-devices'
              ? 'View reports for all discovered devices across your network.'
              : 'Monitor discovered network links, interface status, bandwidth, and connectivity across your infrastructure.'
          }
        />

        {/* Tabs */}
        <div className="flex gap-6 border-b border-white/10">
          <button
            type="button"
            onClick={() => setView('all-devices')}
            className={`pb-3 text-sm transition ${
              view === 'all-devices'
                ? 'border-b-2 border-white font-medium text-white'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            All Devices
          </button>

          <button
            type="button"
            onClick={() => setView('link-health')}
            className={`pb-3 text-sm transition ${
              view === 'link-health'
                ? 'border-b-2 border-white font-medium text-white'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            Link Health
          </button>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 gap-5 md:grid-cols-4">

          {view === 'all-devices' ? (
            <>
              <SummaryStatCard
                title="Total Devices"
                value="120"
                subtitle="Discovered devices"
                icon={Activity}
                gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
              />

              <SummaryStatCard
                title="Offline Devices"
                value="8"
                subtitle="Currently unreachable"
                icon={XCircle}
                gradient="linear-gradient(135deg,#EF4444,#DC2626)"
              />

              <SummaryStatCard
                title="Online Devices"
                value="112"
                subtitle="Currently connected"
                icon={CheckCircle2}
                gradient="linear-gradient(135deg,#22C55E,#16A34A)"
              />
            </>
          ) : (
            <>
              <SummaryStatCard
                title="Total Links"
                value="15"
                subtitle="Discovered links"
                icon={Activity}
                gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
              />

              <SummaryStatCard
                title="Active Links"
                value="13"
                subtitle="Operational"
                icon={CheckCircle2}
                gradient="linear-gradient(135deg,#22C55E,#16A34A)"
              />

              <SummaryStatCard
                title="Down Links"
                value="2"
                subtitle="Needs attention"
                icon={XCircle}
                gradient="linear-gradient(135deg,#EF4444,#DC2626)"
              />
            </>
          )}

          {/* Spacer */}
          <div className="hidden md:block" />
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="rounded-lg bg-white/10 px-4 py-2 text-white outline-none"
          />

          <button
            type="button"
            onClick={handleRunReport}
            disabled={isRunning}
            className="flex items-center gap-2 rounded-lg bg-white px-4 py-2 font-medium text-black transition disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isRunning && <Loader2 className="h-4 w-4 animate-spin" />}
            {isRunning ? 'Running...' : 'Run Report'}
          </button>

          <button
            type="button"
            onClick={handleExport}
            disabled={isExporting}
            className="flex items-center gap-2 rounded-lg bg-[#ffb100] px-4 py-2 font-medium text-black transition disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isExporting && <Loader2 className="h-4 w-4 animate-spin" />}
            {isExporting ? 'Exporting...' : 'Export'}
          </button>
        </div>

        {/* Status message */}
        {statusMessage && (
          <div
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm ${
              statusMessage.type === 'success'
                ? 'bg-green-500/10 text-green-400'
                : 'bg-red-500/10 text-red-400'
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

        {view === 'all-devices' ? (
          <AllDevicesReportTable />
        ) : (
          <LinkHealthReportTable reports={reports} />
        )}

      </div>
    </main>
  )
}