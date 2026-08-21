import { useState } from 'react'
import { Activity, CheckCircle2, XCircle } from 'lucide-react'

import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { AllDevicesReportTable } from '../components/reports/AllDevicesReportTable'
import { LinkHealthReportTable } from '../components/reports/LinkHealthReportTable'
import { reports } from '../data/reports'

type ReportView = 'all-devices' | 'link-health'

export function ReportsPage() {
  const [view, setView] = useState<ReportView>('all-devices')

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
            className="rounded-lg bg-white/10 px-4 py-2 text-white outline-none"
          />

          <button className="rounded-lg bg-white px-4 py-2 font-medium text-black">
            Run Report
          </button>

          <button className="rounded-lg bg-[#ffb100] px-4 py-2 font-medium text-black">
            Export
          </button>
        </div>

        {view === 'all-devices' ? (
          <AllDevicesReportTable />
        ) : (
          <LinkHealthReportTable reports={reports} />
        )}

      </div>
    </main>
  )
}