import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { CheckCircle2, KeyRound, Power, ServerCog, XCircle } from 'lucide-react'
import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { NcpaDevicesTable } from '../components/ncpa-deployment/NcpaDevicesTable'
import { DeploymentHistoryTable } from '../components/ncpa-deployment/DeploymentHistoryTable'
import { DeploymentRunBanner } from '../components/ncpa-deployment/DeploymentRunBanner'
import { DeploymentRunDrawer } from '../components/ncpa-deployment/DeploymentRunDrawer'
import { DeployWizard, type WizardStep } from '../components/ncpa-deployment/DeployWizard'
import { useNcpaDeploymentStatus } from '../hooks/useNcpaDeploymentStatus'
import { useNcpaPluginState } from '../hooks/useNcpaPluginState'
import { errorMessage } from '../lib/api'
import { getNcpaDevices, getRuns } from '../lib/ncpaDeploymentApi'
import type { NcpaDevice, StartResult } from '../types/ncpaDeployment'

type Tab = 'devices' | 'history'

type WizardOptions = {
  initialSelection: number[] | null
  startStep: WizardStep
  verifyOnly: boolean
}

export function NcpaDeploymentPage() {
  const ncpaPlugin = useNcpaPluginState()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab: Tab = searchParams.get('tab') === 'history' ? 'history' : 'devices'
  const openRunId = Number(searchParams.get('run')) || null

  const [devices, setDevices] = useState<NcpaDevice[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  // Bumped to reload the device list.
  const [devicesKey, setDevicesKey] = useState(0)
  const [checked, setChecked] = useState<Set<number>>(new Set())
  const [wizard, setWizard] = useState<WizardOptions | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [historyKey, setHistoryKey] = useState(0)
  const [historyCounts, setHistoryCounts] = useState<{ total: number; needsReview: number } | null>(null)

  const status = useNcpaDeploymentStatus(true)
  const isRunning = status.run?.status === 'Running'

  const loadDevices = useCallback(() => setDevicesKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    getNcpaDevices()
      .then((data) => {
        if (cancelled) return
        setDevices(data)
        setLoadError(null)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(errorMessage(err, 'Unable to load NCPA devices.'))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [devicesKey])

  // Only devices that can still be deployed stay selected (one may have just been deployed).
  const deployableIds = new Set(devices.filter((d) => d.deployable).map((d) => d.id))
  const selected = new Set([...checked].filter((id) => deployableIds.has(id)))

  // Tab pill: runs waiting for review (or all runs when none are waiting).
  useEffect(() => {
    getRuns({ page: 1, perPage: 1 })
      .then((data) => setHistoryCounts({ total: data.total, needsReview: data.needsReview }))
      .catch(() => {})
  }, [historyKey])

  // While a run is going, each device moving on changes the device list;
  // when it finishes, the history changes too.
  const runSignature = status.run
    ? `${status.run.id}:${status.run.status}:${status.run.devices.map((d) => d.outcome).join(',')}`
    : ''
  const lastSignature = useRef('')
  useEffect(() => {
    if (!runSignature || runSignature === lastSignature.current) return
    const firstLoad = lastSignature.current === ''
    lastSignature.current = runSignature
    if (firstLoad) return
    loadDevices()
    setHistoryKey((k) => k + 1)
  }, [runSignature, loadDevices])

  const setTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', next)
    params.delete('run')
    setSearchParams(params)
  }

  const openRun = (runId: number) => {
    const params = new URLSearchParams(searchParams)
    params.set('tab', 'history')
    params.set('run', String(runId))
    setSearchParams(params)
  }

  const closeRun = () => {
    const params = new URLSearchParams(searchParams)
    params.delete('run')
    setSearchParams(params)
  }

  const openWizard = (options: Partial<WizardOptions>) => {
    setNotice(null)
    setWizard({ initialSelection: null, startStep: 0, verifyOnly: false, ...options })
  }

  const handleStarted = (result: StartResult) => {
    setWizard(null)
    setChecked(new Set())
    const names = (id: number) => devices.find((d) => d.id === id)?.hostname ?? `Device ${id}`
    setNotice(
      result.rejected.length
        ? `Deployment started for ${result.started} device(s). Not started: ${result.rejected
            .map((r) => `${names(r.device_id)} (${r.reason})`)
            .join(', ')}.`
        : null,
    )
    loadDevices()
    setHistoryKey((k) => k + 1)
  }

  const ready = devices.filter((d) => d.deployable && d.trusted).length
  const deployed = devices.filter((d) => d.agentStatus === 'Deployed NCPA').length
  const down = devices.filter((d) => d.agentStatus === 'Deployment Failed' && d.lastOutcome === 'Down').length
  const failed = devices.filter((d) => d.agentStatus === 'Deployment Failed' && d.lastOutcome !== 'Down').length
  const hasDeployable = devices.some((d) => d.deployable)

  const tabs = [
    { id: 'devices' as const, label: 'Devices', count: isLoading ? undefined : String(devices.length) },
    {
      id: 'history' as const,
      label: 'Deployment History',
      count: historyCounts
        ? historyCounts.needsReview > 0
          ? `${historyCounts.needsReview} to review`
          : String(historyCounts.total)
        : undefined,
    },
  ]

  return (
    <main className="ml-55 flex-1 space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <PageHeader
          title="NCPA Deployment"
          description="Install the NCPA agent on discovered Linux devices over SSH."
        />
        <button
          type="button"
          onClick={() => openWizard({})}
          disabled={isRunning || !hasDeployable}
          title={isRunning ? 'A deployment is already running.' : !hasDeployable ? 'No devices are waiting for NCPA.' : undefined}
          className="flex items-center gap-2 rounded-lg bg-[#ffb100] px-4 py-2 text-sm font-semibold text-gray-900 hover:bg-[#f0a500] disabled:cursor-default disabled:opacity-50"
        >
          <ServerCog className="h-4 w-4" /> Deploy NCPA
        </button>
      </div>

      {loadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
          {loadError}
        </div>
      )}
      {ncpaPlugin === 'not-enabled' && (
        <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          The check_ncpa plugin is not enabled in Plugin Manager. The agent can still be installed, but its CPU, memory
          and disk checks will not be monitored until you{' '}
          <Link to="/plugins" className="font-semibold underline">enable check_ncpa</Link>.
        </div>
      )}
      {notice && (
        <div role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          {notice}
        </div>
      )}

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-5">
        <SummaryStatCard title="Eligible Devices" value={isLoading ? '—' : String(devices.length)} subtitle="Linux hosts with SSH" icon={ServerCog} gradient="linear-gradient(135deg,#FFB100,#F59E0B)" />
        <SummaryStatCard title="Ready to Deploy" value={isLoading ? '—' : String(ready)} subtitle="host key trusted" icon={KeyRound} gradient="linear-gradient(135deg,#3B82F6,#2563EB)" />
        <SummaryStatCard title="Deployed" value={isLoading ? '—' : String(deployed)} subtitle="agent installed" icon={CheckCircle2} gradient="linear-gradient(135deg,#22C55E,#16A34A)" />
        <SummaryStatCard title="Failed" value={isLoading ? '—' : String(failed)} subtitle="need attention" icon={XCircle} gradient="linear-gradient(135deg,#FF4D4D,#DC2626)" />
        <SummaryStatCard title="Down" value={isLoading ? '—' : String(down)} subtitle="unreachable on last run" icon={Power} gradient="linear-gradient(135deg,#6B7280,#4B5563)" />
      </div>

      {isRunning && status.run && (
        <DeploymentRunBanner
          run={status.run}
          isCancelling={status.isCancelling}
          cancelError={status.cancelError}
          onCancel={status.cancel}
        />
      )}

      <div className="border-b border-gray-200 dark:border-white/10">
        <div className="flex gap-8" role="tablist">
          {tabs.map((t) => {
            const active = tab === t.id
            return (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-2 border-b-2 px-1 pb-3 text-sm font-medium transition ${
                  active
                    ? 'border-[#ffb100] text-gray-900 dark:text-white'
                    : 'border-transparent text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'
                }`}
              >
                {t.label}
                {t.count !== undefined && (
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs ${
                      active ? 'bg-[#ffb100]/20 text-[#b37b00] dark:text-[#ffb100]' : 'bg-gray-100 text-gray-500 dark:bg-white/10 dark:text-gray-400'
                    }`}
                  >
                    {t.count}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {tab === 'devices' ? (
        <NcpaDevicesTable
          devices={devices}
          isLoading={isLoading}
          isRunning={isRunning}
          selected={selected}
          onSelectedChange={setChecked}
          onDeploySelected={() => openWizard({ initialSelection: [...selected] })}
          onVerify={(id) => openWizard({ initialSelection: [id], startStep: 1, verifyOnly: true })}
          onRetry={(id) => openWizard({ initialSelection: [id] })}
        />
      ) : (
        <DeploymentHistoryTable refreshKey={historyKey} onSelectRun={openRun} />
      )}

      {openRunId !== null && (
        <DeploymentRunDrawer
          key={openRunId}
          runId={openRunId}
          devices={devices}
          isRunning={isRunning}
          onClose={closeRun}
          onChanged={() => setHistoryKey((k) => k + 1)}
          onRetry={(ids) => {
            closeRun()
            openWizard({ initialSelection: ids })
          }}
          onNewLogin={(id) => {
            closeRun()
            openWizard({ initialSelection: [id], startStep: 2 })
          }}
        />
      )}

      {wizard && (
        <DeployWizard
          devices={devices}
          initialSelection={wizard.initialSelection}
          startStep={wizard.startStep}
          verifyOnly={wizard.verifyOnly}
          onClose={() => setWizard(null)}
          onDevicesChanged={loadDevices}
          onStarted={handleStarted}
        />
      )}
    </main>
  )
}
