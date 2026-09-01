import { useState } from 'react'
import { Activity, CheckCircle2, XCircle, Loader2 } from 'lucide-react'

import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { ExportMenu } from '../components/shared/ExportMenu'
import { AllDevicesReportTable } from '../components/reports/AllDevicesReportTable'
import { LinkHealthReportTable } from '../components/reports/LinkHealthReportTable'
import { reports } from '../data/reports'
import { useSystemSettings } from '../contexts/SystemSettingsContext'
import { exportRows } from '../utils/exportData'
import type { ExportFormat } from '../types/settings'

type ReportView = 'all-devices' | 'link-health'

export function ReportsPage() {
  const { settings } = useSystemSettings()
  const [view, setView] = useState<ReportView>('all-devices')
  const [selectedDate, setSelectedDate] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const handleRunReport = async () => {
    setIsRunning(true)
    setStatusMessage(null)
    try {
      await abang()
      setStatusMessage({ type: 'success', text: 'Report generated successfully.' })
    } catch (err) {
      setStatusMessage({ type: 'error', text: 'Could not run report. Please try again.' })
    } finally {
      setIsRunning(false)
    }
  }

  const handleExport = (format: ExportFormat) => {
    const rows = view === 'all-devices' ? [] : reports
    const filename = view === 'all-devices' ? 'all-devices-report' : 'link-health-report'

    try {
      exportRows(rows, format, filename)
      setStatusMessage({ type: 'success', text: 'Export ready for download.' })
    } catch (err) {
      setStatusMessage({ type: 'error', text: 'Export failed. Please try again.' })
    }
  }

  const abang = () => new Promise((resolve) => setTimeout(resolve, 900))

  return (
    <main className="ml-55 flex-1">
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
        <div className="flex gap-6 border-b border-gray-200 dark:border-white/10">
          <button type="button" onClick={() => setView('all-devices')}
            className={`pb-3 text-sm transition ${view === 'all-devices' ? 'border-b-2 border-gray-900 font-medium text-gray-900 dark:border-white dark:text-white' : 'text-gray-500 hover:text-gray-900 dark:text-white/60 dark:hover:text-white'}`}>
            All Devices
          </button>
          <button type="button" onClick={() => setView('link-health')}
            className={`pb-3 text-sm transition ${view === 'link-health' ? 'border-b-2 border-gray-900 font-medium text-gray-900 dark:border-white dark:text-white' : 'text-gray-500 hover:text-gray-900 dark:text-white/60 dark:hover:text-white'}`}>
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

          <div className="hidden md:block" />
        </div>

        {/* Actions */}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-gray-900 outline-none shadow-sm dark:border-white/10 dark:bg-[#171B20] dark:text-white"
          />

          <button
            type="button"
            onClick={handleRunReport}
            disabled={isRunning}
            className="flex items-center gap-2 rounded-lg bg-white border border-gray-300 px-4 py-2 font-medium text-gray-800 shadow-sm transition hover:bg-gray-50 hover:shadow dark:bg-[#171B20] dark:border-white/10 dark:text-white dark:hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer"
          >
            {isRunning && <Loader2 className="h-4 w-4 animate-spin" />}
            {isRunning ? 'Running...' : 'Run Report'}
          </button>

          <ExportMenu
            allowedFormats={settings.exportFormats}
            onExport={handleExport}
            label
            buttonClassName="rounded-lg bg-[#ffb100] px-4 py-2 font-medium text-black shadow-sm transition hover:opacity-90 cursor-pointer"
          />
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

        {view === 'all-devices' ? (
          <AllDevicesReportTable />
        ) : (
          <LinkHealthReportTable reports={reports} />
        )}

      </div>
    </main>
  )
}
