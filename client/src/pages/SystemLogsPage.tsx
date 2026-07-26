import { useMemo, useState } from 'react'
import { PageHeader } from '../components/shared/PageHeader'
import { logs } from '../data/logs'

type LogType = 'all' | 'session' | 'account' | 'network'

export function SystemLogsPage() {
  const [typeFilter, setTypeFilter] = useState<LogType>('all')
  const [selectedLog, setSelectedLog] = useState<any | null>(null)

  const filteredLogs = useMemo(() => {
    if (typeFilter === 'all') return logs
    return logs.filter((log) => log.type === typeFilter)
  }, [typeFilter])

  return (
    <main className="ml-[220px] flex-1 text-white">
      <div className="space-y-6">

        {/* HEADER */}
        <PageHeader
          title="System Logs"
          description="Monitor events and system activities."
        />

        {/* ✅ NEW: TOP TABS (MATCHED STYLE) */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex gap-2">
            {(['all', 'session', 'account', 'network'] as LogType[]).map((type) => (
              <button
                key={type}
                onClick={() => setTypeFilter(type)}
                className={`px-4 py-2 rounded-lg text-sm transition ${
                  typeFilter === type
                    ? 'bg-white text-black'
                    : 'bg-white/10 text-gray-300 hover:bg-white/20'
                }`}
              >
                {type === 'all'
                  ? 'All Types'
                  : type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* CONTENT */}
        <div className="flex gap-6">

          {/* LEFT: LOG LIST */}
          <div className="flex-1 space-y-4">

            {/* TABLE HEADER */}
            <div className="grid grid-cols-[1fr_180px_120px] px-4 text-sm text-gray-400">
              <span>Activity</span>
              <span>Timestamp</span>
              <span>Tag ID</span>
            </div>

            {/* LOG ITEMS */}
            <div className="space-y-2">
              {filteredLogs.map((log) => (
                <div
                  key={log.id}
                  onClick={() => setSelectedLog(log)}
                  className="grid grid-cols-[1fr_180px_120px] items-center px-4 py-3 rounded-lg cursor-pointer bg-white/5 hover:bg-white/10 transition"
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-6 h-6 flex items-center justify-center rounded ${
                        log.type === 'account'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : log.type === 'network'
                          ? 'bg-orange-500/20 text-orange-400'
                          : 'bg-red-500/20 text-red-400'
                      }`}
                    >
                      !
                    </div>

                    <span className="text-sm text-white">
                      <strong className="text-white">{log.title}</strong>{' '}
                      <span className="text-gray-300">{log.description}</span>
                    </span>
                  </div>

                  <span className="text-gray-400 text-sm">
                    {log.timestamp}
                  </span>

                  <span className="text-gray-400 text-sm">
                    {log.tagId}
                  </span>
                </div>
              ))}
            </div>

          </div>

          {/* RIGHT PANEL */}
          <div className="w-[300px] bg-white/5 rounded-xl p-4 space-y-4">

            {selectedLog ? (
              <>
                <h3 className="text-sm font-semibold border-b border-white/10 pb-2 text-white">
                  {selectedLog.title}
                </h3>

                <p className="text-sm text-gray-300">
                  {selectedLog.description}
                </p>

                <div className="text-xs text-gray-400 space-y-1">
                  <p>Tag ID: {selectedLog.tagId}</p>
                  <p>Date & Time: {selectedLog.timestamp}</p>
                </div>

                <div className="flex gap-2 pt-4">
                  <button className="flex-1 bg-white text-black py-2 rounded-md">
                    Exit
                  </button>

                  <button className="flex-1 bg-white/10 py-2 rounded-md text-white">
                    Log out
                  </button>
                </div>
              </>
            ) : (
              <div className="text-gray-400 text-sm">
                Select a log to view details
              </div>
            )}

          </div>

        </div>
      </div>
    </main>
  )
}