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

/** "check_ssh" → "SSH", "check_ntp_time" → "Ntp Time": the plugin's name without the check_ prefix. */
function shortName(pluginName: string) {
  const name = pluginName.replace(/\.py$/i, '').replace(/^check_/i, '').replace(/_/g, ' ').trim()
  if (!name) return pluginName
  return name.length <= 4 ? name.toUpperCase() : name.replace(/\b\w/g, (c) => c.toUpperCase())
}

/** The plugin's Plugin Manager display name, or its short name when none was set. */
function titleFor(plugin: AddedPlugin) {
  return plugin.displayName === plugin.pluginName ? shortName(plugin.pluginName) : plugin.displayName
}

function formatValue(value: number | null, unit: string | null) {
  if (value == null) return '—'
  const digits = Math.abs(value) >= 100 ? 0 : Math.abs(value) >= 1 ? 2 : 3
  return `${value.toFixed(digits)}${unit ? ` ${unit}` : ''}`
}

/** The metric a card leads with: the first averaged one, else the first. */
function primaryMetric(plugin: AddedPlugin): PluginMetric | null {
  return plugin.metrics.find((m) => m.averaged) ?? plugin.metrics[0] ?? null
}

const STATUS_HEADLINE: Record<AddedPlugin['worstState'], string> = {
  ok: 'Working normally',
  warning: 'Needs attention',
  critical: 'Not working',
  unknown: 'Status unknown',
}

function plural(count: number, noun: string) {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}

/** One plain sentence on how the plugin's checks are doing. */
function statusSentence(plugin: AddedPlugin) {
  const { total, ok, warning, critical, unknown } = plugin
  if (ok === total) return total === 1 ? 'The check is passing.' : `All ${total} checks are passing.`
  const problems = [
    critical && `${critical} failing`,
    warning && `${warning} with a warning`,
    unknown && `${unknown} with an unknown result`,
  ].filter(Boolean).join(', ')
  return `${ok} of ${plural(total, 'check')} passing. ${problems}.`
}

function StatusSummary({ plugin }: { plugin: AddedPlugin }) {
  const state = STATE_STYLE[plugin.worstState]
  const counts = [
    { label: 'OK', count: plugin.ok, badge: STATE_STYLE.ok.badge },
    { label: 'Warning', count: plugin.warning, badge: STATE_STYLE.warning.badge },
    { label: 'Critical', count: plugin.critical, badge: STATE_STYLE.critical.badge },
    { label: 'Unknown', count: plugin.unknown, badge: STATE_STYLE.unknown.badge },
  ].filter((c) => c.count > 0)

  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
      <span className={`rounded-full px-3 py-1 text-sm font-semibold text-white ${state.badge}`}>
        {STATUS_HEADLINE[plugin.worstState]}
      </span>
      <p className="text-base font-medium text-[var(--text)]">{statusSentence(plugin)}</p>
      <div className="flex flex-wrap justify-center gap-2">
        {counts.map((c) => (
          <span key={c.label} className="flex items-center gap-1.5 text-sm text-[var(--text-muted)]">
            <span className={`h-2 w-2 rounded-full ${c.badge}`} />
            {c.count} {c.label}
          </span>
        ))}
      </div>
      <p className="text-xs text-[var(--text-muted)]">
        This check reports pass or fail only, so there is no graph to show.
      </p>
    </div>
  )
}

function PluginCard({ plugin, onOpen }: { plugin: AddedPlugin; onOpen: () => void }) {
  const state = STATE_STYLE[plugin.worstState]
  const metric = primaryMetric(plugin)

  let value = STATUS_HEADLINE[plugin.worstState]
  let caption = statusSentence(plugin)
  if (metric?.averaged) {
    value = formatValue(metric.currentAvg, metric.unit)
    caption = metric.serviceCount === 1
      ? `${metric.metric} on ${metric.current[0].hostname}`
      : `avg ${metric.metric} across ${metric.serviceCount} services`
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
        <span className="text-sm text-[var(--text-muted)]">{titleFor(plugin)}</span>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-medium text-white ${state.badge}`}>
          {plugin.worstState === 'ok' ? `${plugin.ok}/${plugin.total} OK` : `${plugin[plugin.worstState]} ${state.label}`}
        </span>
      </div>
      <span className={`${metric?.averaged ? 'text-2xl' : 'text-xl'} font-bold text-[var(--text)]`}>{value}</span>
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
    return null
  }
  return (
    <div className="max-h-48 overflow-y-auto">
      <p className="mb-2 text-sm font-medium text-[var(--text)]">Latest readings by host</p>
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
          title={titleFor(open)}
          unit={primary?.averaged ? primary.unit ?? '' : ''}
          datasourceLabel={series.length > 0 ? `${titleFor(open)} — average across services` : `${titleFor(open)} — status of ${plural(open.total, 'check')}`}
          series={series}
          seriesData={seriesData}
          hours={hours}
          onHoursChange={onHoursChange}
          isLoading={isLoading}
          isConfigured={series.length > 0}
          emptyContent={<StatusSummary plugin={open} />}
          details={<PerHostValues plugin={open} />}
          onClose={() => setOpenName(null)}
        />
      )}
    </section>
  )
}
