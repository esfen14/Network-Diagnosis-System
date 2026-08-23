import { useMemo, useState } from 'react'
import { PageHeader } from '../components/shared/PageHeader'
import { logs } from '../data/logs'

type LogTab =
  | 'activity'
  | 'configurationChange'
  | 'networkDiscovery'
  | 'ncpaDeployment'
  | 'exportLog'

type Log = (typeof logs)[number]

export function SystemLogsPage() {
  const [activeTab, setActiveTab] = useState<LogTab>('activity')
  const [selectedLog, setSelectedLog] = useState<Log | null>(null)

  // Date range filters
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      // Filter according to the selected tab
      const matchesTab = log.category === activeTab

      // Extract YYYY-MM-DD from the log timestamp
      const logDate = log.timestamp.split(' ')[0]

      // Start date filter
      const matchesStartDate =
        startDate === '' || logDate >= startDate

      // End date filter
      const matchesEndDate =
        endDate === '' || logDate <= endDate

      return matchesTab && matchesStartDate && matchesEndDate
    })
  }, [activeTab, startDate, endDate])

  const getTabLabel = (tab: LogTab) => {
    switch (tab) {
      case 'activity':
        return 'Activity Log'

      case 'configurationChange':
        return 'Configuration Change'

      case 'networkDiscovery':
        return 'Network Discovery'

      case 'ncpaDeployment':
        return 'NCPA Deployment'

      case 'exportLog':
        return 'Export Log'
    }
  }

  return (
    <main className="ml-55 flex-1 text-white">
      <div className="space-y-6">

        {/* HEADER */}
        <PageHeader
          title="System Logs"
          description="Monitor events and system activities."
        />

        {/* TABS + DATE RANGE */}
        <div className="flex items-end justify-between border-b border-white/10">

          {/* TABS */}
          <div className="flex gap-6">

            {(
              [
                'activity',
                'configurationChange',
                'networkDiscovery',
                'ncpaDeployment',
                'exportLog',
              ] as LogTab[]
            ).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => {
                  setActiveTab(tab)
                  setSelectedLog(null)
                }}
                className={`pb-3 text-sm transition ${
                  activeTab === tab
                    ? 'border-b-2 border-white font-medium text-white'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {getTabLabel(tab)}
              </button>
            ))}

          </div>

          {/* DATE RANGE */}
          <div className="flex items-end gap-3 pb-2">

            {/* START DATE */}
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400">
                Start Date
              </label>

              <input
                type="text"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                placeholder="YYYY-MM-DD"
                maxLength={10}
                className="w-36.25 rounded-lg bg-white/10 px-3 py-2 text-sm text-white placeholder-gray-500 outline-none transition focus:bg-white/15"
              />
            </div>

            {/* END DATE */}
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-400">
                End Date
              </label>

              <input
                type="text"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                placeholder="YYYY-MM-DD"
                maxLength={10}
                className="w-36.25 rounded-lg bg-white/10 px-3 py-2 text-sm text-white placeholder-gray-500 outline-none transition focus:bg-white/15"
              />
            </div>

          </div>
        </div>

        {/* CONTENT */}
        <div className="flex gap-6">

          {/* LOG TABLE */}
          <div className="flex-1 space-y-4">

            {/* TABLE HEADER */}
            <div className="grid grid-cols-[180px_1fr_120px] gap-4 px-4 text-sm text-gray-400">
              <span>
                Timestamp
              </span>

              <span>
                {getTabLabel(activeTab)}
              </span>

              <span>
                Tag ID
              </span>
            </div>

            {/* TABLE ROWS */}
            <div className="space-y-2">

              {filteredLogs.map((log) => (
                <div
                  key={log.id}
                  onClick={() => setSelectedLog(log)}
                  className="grid grid-cols-[180px_1fr_120px] items-center gap-4 rounded-lg bg-white/5 px-4 py-3 transition cursor-pointer hover:bg-white/10"
                >

                  {/* TIMESTAMP */}
                  <span className="text-sm text-gray-400">
                    {log.timestamp}
                  </span>

                  {/* LOG INFORMATION */}
                  <div className="flex items-center gap-3">

                    <LogIcon type={log.type} />

                    <div className="flex flex-col">

                      <span className="text-sm font-medium text-white">
                        {log.title}
                      </span>

                      <span className="text-xs text-gray-400">
                        {log.description}
                      </span>

                    </div>

                  </div>

                  {/* TAG ID */}
                  <span className="text-sm text-gray-400">
                    {log.tagId}
                  </span>

                </div>
              ))}

            </div>

            {/* EMPTY STATE */}
            {filteredLogs.length === 0 && (
              <div className="py-10 text-center text-sm text-gray-500">
                No logs found for the selected date range.
              </div>
            )}

          </div>

          {/* RIGHT DETAILS PANEL */}
          <div className="w-75 space-y-4 rounded-xl bg-white/5 p-4">

            {selectedLog ? (
              <>

                {/* TITLE */}
                <h3 className="border-b border-white/10 pb-2 text-sm font-semibold text-white">
                  {selectedLog.title}
                </h3>

                {/* DESCRIPTION */}
                <p className="text-sm text-gray-300">
                  {selectedLog.description}
                </p>

                {/* DETAILS */}
                <div className="space-y-1 text-xs text-gray-400">

                  <p>
                    Type: {selectedLog.type}
                  </p>

                  <p>
                    Tag ID: {selectedLog.tagId}
                  </p>

                  <p>
                    Date & Time: {selectedLog.timestamp}
                  </p>

                  <p>
                    User: {selectedLog.user}
                  </p>

                </div>

                {/* ACTION BUTTONS */}
                <div className="flex gap-2 pt-4">

                  <button
                    type="button"
                    onClick={() => setSelectedLog(null)}
                    className="flex-1 rounded-md bg-white py-2 text-black transition hover:bg-gray-200"
                  >
                    Exit
                  </button>

                  <button
                    type="button"
                    className="flex-1 rounded-md bg-white/10 py-2 text-white transition hover:bg-white/20"
                  >
                    Log out
                  </button>

                </div>

              </>
            ) : (
              <div className="text-sm text-gray-400">
                Select a log to view details
              </div>
            )}

          </div>

        </div>
      </div>
    </main>
  )
}

/* LOG ICON */
function LogIcon({ type }: { type: string }) {
  const iconStyle =
    type === 'account'
      ? 'bg-yellow-500/20 text-yellow-400'
      : type === 'network'
      ? 'bg-orange-500/20 text-orange-400'
      : type === 'deployment'
      ? 'bg-blue-500/20 text-blue-400'
      : type === 'configuration'
      ? 'bg-purple-500/20 text-purple-400'
      : type === 'export'
      ? 'bg-green-500/20 text-green-400'
      : 'bg-red-500/20 text-red-400'

  return (
    <div
      className={`flex h-6 w-6 items-center justify-center rounded ${iconStyle}`}
    >
      !
    </div>
  )
}