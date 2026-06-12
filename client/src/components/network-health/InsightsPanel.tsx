const insights = [
  {
    message: '66 devices are unreachable (check_ping)',
    time: 'Just now',
    color: 'bg-blue-500',
  },
  {
    message: 'Average latency reached 208ms across all devices.',
    time: '59 minutes ago',
    color: 'bg-pink-500',
  },
  {
    message: '47 devices have reached critical state',
    time: '12 hours ago',
    color: 'bg-gray-500',
  },
  {
    message: 'Average network hop path length is 6',
    time: 'Today, 11:59 AM',
    color: 'bg-emerald-500',
  },
  {
    message: 'Overall network condition is stable',
    time: 'March 24, 2026',
    color: 'bg-white',
  },
]

export function InsightsPanel() {
  return (
    <aside className="hidden w-72 shrink-0 border-l border-white/10 xl:block">
      <div className="sticky top-0 p-4">
        <h3 className="mb-4 text-sm font-semibold text-white">Network Health Insights</h3>
        <div className="space-y-4">
          {insights.map((item, i) => (
            <div key={i} className="flex gap-3">
              <div className={`mt-1 h-8 w-8 shrink-0 rounded-full ${item.color}`} />
              <div>
                <p className="text-sm leading-snug text-white">{item.message}</p>
                <p className="mt-1 text-xs text-gray-500">{item.time}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  )
}
