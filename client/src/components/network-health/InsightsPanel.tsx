const supportedChecks = [
  'Ping (availability & latency)',
  'Resource Usage (CPU, memory)',
  'Process and User Monitoring',
  'Network Connections',
  'Route Tracing',
]

const insights = [
  { message: '66 devices are unreachable (check_ping)',         time: 'Just now',         color: 'bg-blue-500'    },
  { message: 'Average latency reached 208ms across all devices.',time: '59 minutes ago',   color: 'bg-pink-500'    },
  { message: '47 devices have reached critical state',           time: '12 hours ago',     color: 'bg-gray-400'    },
  { message: 'Average network hop path length is 6',             time: 'Today, 11:59 AM',  color: 'bg-emerald-500' },
  { message: 'Overall network condition is stable',              time: 'March 24, 2026',   color: 'bg-gray-300'    },
]

export function InsightsPanel() {
  return (
    <aside className="hidden w-72 shrink-0 border-l border-[var(--border)] xl:block">
      <div className="sticky top-0 p-4">
        <h3 className="mb-4 text-sm font-semibold text-[var(--text)]">Network Health Insights</h3>
        <div className="space-y-4">
          {insights.map((item, i) => (
            <div key={i} className="flex gap-3">
              <div className={`mt-1 h-8 w-8 shrink-0 rounded-full ${item.color}`} />
              <div>
                <p className="text-sm leading-snug text-[var(--text)]">{item.message}</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">{item.time}</p>
              </div>
            </div>
          ))}
        </div>
        <h3 className="mb-3 mt-8 text-sm font-semibold text-[var(--text)]">Current Supported Checks</h3>
        <ul className="space-y-2">
          {supportedChecks.map((check) => (
            <li key={check} className="text-sm text-[var(--text-muted)]">{check}</li>
          ))}
        </ul>
      </div>
    </aside>
  )
}
