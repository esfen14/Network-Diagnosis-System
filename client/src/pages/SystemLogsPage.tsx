import { useMemo, useState } from 'react'
import { PageHeader } from '../components/shared/PageHeader'
import { logs } from '../data/logs'

type LogTab =
  | 'all'
  | 'activity'
  | 'configurationChange'
  | 'networkDiscovery'
  | 'ncpaDeployment'

type Log = (typeof logs)[number]

export function SystemLogsPage() {
  const [activeTab, setActiveTab] = useState<LogTab>('all')
  const [selectedLog, setSelectedLog] = useState<Log | null>(null)

  const filteredLogs = useMemo(() => {
    if (activeTab === 'all') {
      return logs
    }

    return logs.filter((log) => log.category === activeTab)
  }, [activeTab])

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
      default:
        return 'All Types'
    }
  }

  return (
    <main className="ml-[220px] flex-1 text-white">
      <div className="space-y-6">

        {/* HEADER */}
        <PageHeader
          title="System Logs"
          description="Monitor events and system activities."
        />

        {/* TABS */}
        <div className="flex gap-6 border-b border-white/10">
          {(
            [
              'all',
              'activity',
              'configurationChange',
              'networkDiscovery',
              'ncpaDeployment',
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

        {/* CONTENT */}
        <div className="flex gap-6">

          {/* LOG TABLE */}
          <div className="flex-1 space-y-4">

            {/* ALL TYPES */}
            {activeTab === 'all' && (
              <>
                {/* TABLE HEADER */}
                <div className="grid grid-cols-[180px_1fr_120px] gap-4 px-4 text-sm text-gray-400">
                  <span>Timestamp</span>
                  <span>Type</span>
                  <span>Tag ID</span>
                </div>

                {/* TABLE ROWS */}
                <div className="space-y-2">
                  {filteredLogs.map((log) => (
                    <div
                      key={log.id}
                      onClick={() => setSelectedLog(log)}
                      className="grid grid-cols-[180px_1fr_120px] gap-4 items-center px-4 py-3 rounded-lg cursor-pointer bg-white/5 hover:bg-white/10 transition"
                    >
                      {/* TIMESTAMP */}
                      <span className="text-gray-400 text-sm">
                        {log.timestamp}
                      </span>

                      {/* TYPE */}
                      <div className="flex items-center gap-3">
                        <LogIcon type={log.type} />

                        <div className="flex flex-col">
                          <span className="text-sm text-white font-medium">
                            {log.title}
                          </span>

                          <span className="text-xs text-gray-400">
                            {log.description}
                          </span>
                        </div>
                      </div>

                      {/* TAG ID */}
                      <span className="text-gray-400 text-sm">
                        {log.tagId}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* INDIVIDUAL TABS */}
            {activeTab !== 'all' && (
              <>
                {/* TABLE HEADER */}
                <div className="grid grid-cols-[180px_1fr_120px] gap-4 px-4 text-sm text-gray-400">
                  <span>Timestamp</span>
                  <span>{getTabLabel(activeTab)}</span>
                  <span>Tag ID</span>
                </div>

                {/* TABLE ROWS */}
                <div className="space-y-2">
                  {filteredLogs.map((log) => (
                    <div
                      key={log.id}
                      onClick={() => setSelectedLog(log)}
                      className="grid grid-cols-[180px_1fr_120px] gap-4 items-center px-4 py-3 rounded-lg cursor-pointer bg-white/5 hover:bg-white/10 transition"
                    >
                      {/* TIMESTAMP */}
                      <span className="text-gray-400 text-sm">
                        {log.timestamp}
                      </span>

                      {/* LOG */}
                      <div className="flex items-center gap-3">
                        <LogIcon type={log.type} />

                        <div className="flex flex-col">
                          <span className="text-sm text-white font-medium">
                            {log.title}
                          </span>

                          <span className="text-xs text-gray-400">
                            {log.description}
                          </span>
                        </div>
                      </div>

                      {/* TAG ID */}
                      <span className="text-gray-400 text-sm">
                        {log.tagId}
                      </span>
                    </div>
                  ))}
                </div>

                {/* EMPTY STATE */}
                {filteredLogs.length === 0 && (
                  <div className="py-10 text-center text-sm text-gray-500">
                    No logs available for this category.
                  </div>
                )}
              </>
            )}

          </div>

          {/* RIGHT PANEL */}
          <div className="w-[300px] bg-white/5 rounded-xl p-4 space-y-4">

            {selectedLog ? (
              <>
                {/* TITLE */}
                <h3 className="text-sm font-semibold border-b border-white/10 pb-2 text-white">
                  {selectedLog.title}
                </h3>

                {/* DESCRIPTION */}
                <p className="text-sm text-gray-300">
                  {selectedLog.description}
                </p>

                {/* DETAILS */}
                <div className="text-xs text-gray-400 space-y-1">
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

                {/* ACTIONS */}
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
      : 'bg-red-500/20 text-red-400'

  return (
    <div
      className={`flex h-6 w-6 items-center justify-center rounded ${iconStyle}`}
    >
      !
    </div>
  )
}