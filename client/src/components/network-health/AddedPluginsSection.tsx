import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { AddedPlugin, PluginMetric } from '../../types/networkHealth'
import { MetricGraphModal, type GraphSeriesConfig, type TrendHours } from './MetricGraphModal'
import { MiniSparkline } from './MiniSparkline'

// One widget per plugin added through the Plugin Manager
// (GET /network-health/plugin-trends). Checks that come with the default
// system have their own widgets elsewhere on the page.

const STATE_STYLE: Record<AddedPlugin['worstState'], { label: string; badge: string; color: string }> = {
  ok: { label: 'OK', badge: 'bg-emerald-500', color: '#10B981' },
  warning: { label: 'Warning', badge: 'bg-[#F4A90B]', color: '#F4A90B' },
  critical: { label: 'Critical', badge: 'bg-red-600', color: '#EF4444' },
  unknown: { label: 'Unknown', badge: 'bg-gray-400', color: '#9CA3AF' },
}

const SERIES_COLORS = ['#38BDF8', '#A78BFA', '#10B981', '#F4A90B', '#EF4444']

function formatValue(value: number | null, unit: string | null) {
  if (value == null) return '—'
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 1 ? 2 : 3
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ''}`
}

/** The metric a card leads with: the first averaged one, else the first. */
function primaryMetric(plugin: AddedPlugin): PluginMetric | null {
  return plugin.metrics.find((m) => m.averaged) ?? plugin.metrics[0] ?? null
}

function PluginCard({ plugin, onOpen }: { plugin: AddedPlugin; onOpen: () => void }) {
  const state = STATE_STYLE[plugin.worstState]
  const metric = primaryMetric(plugin)

  let value = '—'
  let caption = 'No performance data reported'
  if (metric?.averaged) {
    value = formatValue(metric.currentAvg, metric.unit)
    caption = metric.serviceCount === 1
      ? `${metric.metric} on ${metric.current[0].hostname}`
      : `avg ${metric.metric} across ${metric.serviceCount} services`
  } else if (metric) {
    caption = `${metric.metric} varies per host — open for values`
  }

  return (
    <div
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onOpen() }}
      className="flex flex-col gap-2 rounded-2xl bg-[var(--card)] border border-[var(--border)] p-4 shadow-sm cursor-pointer transition hover:border-[var(--text-muted)]"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm text-[var(--text-muted)]">{plugin.displayName}</span>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium text-white ${state.badge}`}>
          {plugin.worstState === 'ok' ? `${plugin.ok}/${plugin.total} OK` : `${plugin[plugin.worstState]} ${state.label}`}
        </span>
      </div>
      <span className="text-2xl font-bold text-[var(--text)]">{value}</span>
      <span className="text-xs text-[var(--text-muted)]">{caption}</span>
      {metric?.averaged && (
        <MiniSparkline
          data={metric.points.map((p) => p.avgValue ?? 0)}
          color={state.color}
          gradientId={`plugin-${plugin.pluginName}`}
        />
      )}
    </div>
  )
}

function PerHostValues({ plugin }: { plugin: AddedPlugin }) {
  if (plugin.metrics.length === 0) {
    return <p className="text-sm text-[var(--text-muted)]">This plugin reports no performance data.</p>
  }
  return (
    <div className="max-h-48 overflow-y-auto">
      <p className="mb-2 text-sm font-medium text-[var(--text)]">Current values per service</p>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-[var(--text-muted)]">
            <th className="pb-1 font-normal">Host</th>
            <th className="pb-1 font-normal">Service</th>
            <th className="pb-1 font-normal">Metric</th>
            <th className="pb-1 text-right font-normal">Value</th>
          </tr>
        </thead>
        <tbody>
          {plugin.metrics.flatMap((m) =>
            m.current.map((c) => (
              <tr key={`${m.metric}-${m.unit}-${c.hostname}-${c.service}`} className="border-t border-dashed border-[var(--border)]">
                <td className="py-1 text-[var(--text)]">{c.hostname}</td>
                <td className="py-1 text-[var(--text-muted)]">{c.service}</td>
                <td className="py-1 text-[var(--text-muted)]">{m.metric}</td>
                <td className="py-1 text-right text-[var(--text)]">{formatValue(c.value, m.unit)}</td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  )
}

type AddedPluginsSectionProps = {
  plugins: AddedPlugin[] | null
  error: string | null
  hours: TrendHours
  onHoursChange: (hours: TrendHours) => void
  isLoading: boolean
}

export function AddedPluginsSection({ plugins, error, hours, onHoursChange, isLoading }: AddedPluginsSectionProps) {
  const [openName, setOpenName] = useState<string | null>(null)
  const open = plugins?.find((p) => p.pluginName === openName) ?? null

  // The popup graphs the averaged metrics that share the card's unit.
  const primary = open ? primaryMetric(open) : null
  const graphed = open && primary?.averaged
    ? open.metrics.filter((m) => m.averaged && m.unit === primary.unit)
    : []
  const series: GraphSeriesConfig[] = graphed.map((m, i) => ({
    key: m.metric,
    label: m.metric,
    color: SERIES_COLORS[i % SERIES_COLORS.length],
    precision: 3,
  }))
  const seriesData = Object.fromEntries(graphed.map((m) => [m.metric, m.points]))

  return (
    <section>
      <div className="mb-3 flex items-baseline justify-between gap-4">
        <h3 className="text-lg font-semibold text-[var(--text)]">Added Plugins</h3>
        <Link to="/plugins" className="text-sm text-[#F4A90B] hover:underline">Manage plugins</Link>
      </div>

      {error ? (
        <p className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 text-sm text-[var(--text-muted)]">{error}</p>
      ) : plugins == null ? (
        <p className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 text-sm text-[var(--text-muted)]">Loading…</p>
      ) : plugins.length === 0 ? (
        <p className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5 text-sm text-[var(--text-muted)]">
          No plugin widgets yet. Plugins you enable in the Plugin Manager get their own widget here once their services have reported.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {plugins.map((plugin) => (
            <PluginCard key={plugin.pluginName} plugin={plugin} onOpen={() => setOpenName(plugin.pluginName)} />
          ))}
        </div>
      )}

      {open && (
        <MetricGraphModal
          title={open.displayName}
          unit={primary?.averaged ? primary.unit ?? '' : ''}
          datasourceLabel={`${open.pluginName} — average across services`}
          series={series}
          seriesData={seriesData}
          hours={hours}
          onHoursChange={onHoursChange}
          isLoading={isLoading}
          isConfigured={series.length > 0}
          emptyMessage="This plugin has no time or percentage metric to average — see the per-service values below."
          details={<PerHostValues plugin={open} />}
          onClose={() => setOpenName(null)}
        />
      )}
    </section>
  )
}
