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
    <main className="ml-[220px] flex-1">
      <div className="space-y-6">

        <PageHeader title="System Logs" description="Monitor events and system activities." />

      {/* Tabs */}
      <div className="flex gap-6 border-b border-[var(--border)]">
        {(['all', 'session', 'account', 'network'] as LogType[]).map((type) => (
          <button
            key={type}
            onClick={() => setTypeFilter(type)}
            className={`pb-3 text-sm transition ${
              typeFilter === type
                ? 'border-b-2 border-[var(--text)] font-medium text-[var(--text)]'
                : 'text-[var(--text-muted)] hover:text-[var(--text)]'
            }`}
          >
            {type === 'all' ? 'All Types' : type.charAt(0).toUpperCase() + type.slice(1)}
          </button>
        ))}
      </div>

        <div className="flex gap-6">
          {/* Log list */}
          <div className="flex-1 space-y-4">
            <div className="grid grid-cols-[1fr_180px_120px] px-4 text-sm text-[var(--text-muted)]">
              <span>Activity</span><span>Timestamp</span><span>Tag ID</span>
            </div>
            <div className="space-y-2">

              {filteredLogs.map((log) => (
                <div
                  key={log.id}
                  onClick={() => setSelectedLog(log)}
                  className={`grid grid-cols-[1fr_180px_120px] items-center px-4 py-3 rounded-xl cursor-pointer border transition ${
                    selectedLog?.id === log.id
                      ? 'border-[var(--border)] bg-[var(--hover)]'
                      : 'border-[var(--border)] bg-[var(--card)] hover:bg-[var(--hover)]'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-6 h-6 flex items-center justify-center rounded font-bold text-xs ${
                      log.type === 'account' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300'
                      : log.type === 'network' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300'
                      : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
                    }`}>!</div>
                    <span className="text-sm text-[var(--text)]">
                      <strong>{log.title}</strong>{' '}
                      <span className="text-[var(--text-muted)]">{log.description}</span>
                    </span>
                  </div>
                  <span className="text-[var(--text-muted)] text-sm">{log.timestamp}</span>
                  <span className="text-[var(--text-muted)] text-sm">{log.tagId}</span>
                </div>
              ))}

            </div>
          </div>

          {/* Detail panel */}
          <div className="w-[300px] bg-[var(--card)] border border-[var(--border)] rounded-2xl p-4 space-y-4">
            {selectedLog ? (
              <>
                <h3 className="text-sm font-semibold border-b border-[var(--border)] pb-2 text-[var(--text)]">{selectedLog.title}</h3>
                <p className="text-sm text-[var(--text-muted)]">{selectedLog.description}</p>
                <div className="text-xs text-[var(--text-muted)] space-y-1">
                  <p>Tag ID: {selectedLog.tagId}</p>
                  <p>Date &amp; Time: {selectedLog.timestamp}</p>
                </div>
                <div className="flex gap-2 pt-4">
                  <button onClick={() => setSelectedLog(null)} className="flex-1 bg-[var(--text)] text-[var(--card)] py-2 rounded-lg text-sm">Close</button>
                  <button className="flex-1 bg-[var(--hover)] border border-[var(--border)] py-2 rounded-lg text-sm text-[var(--text)] hover:bg-[var(--card-alt)]">Export</button>
                </div>

              </>
            ) : (
              <div className="text-[var(--text-muted)] text-sm">Select a log to view details</div>
            )}
          </div>
        </div>

      </div>
    </main>
  )
}
