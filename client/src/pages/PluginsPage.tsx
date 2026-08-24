import { useState } from 'react'
import { PageHeader } from '../components/shared/PageHeader'
import { SummaryStatCard } from '../components/shared/SummaryStatCard'
import { availablePlugins, installedPlugins } from '../data/plugins'
import { AvailablePluginsTable } from '../components/plugins/AvailablePluginsTable'
import { InstalledPluginsTable } from '../components/plugins/InstalledPluginsTable'
import {
  Activity,
  HelpCircle,
  CheckCircle2,
  X,
} from 'lucide-react'

type View = 'available' | 'installed'

type PluginState =
  | 'idle'
  | 'confirmAdd'
  | 'adding'
  | 'confirmDelete'
  | 'deleting'
  | 'deleteSuccess'

export function PluginsPage() {
  const [view, setView] = useState<View>('available')
  const [selected, setSelected] = useState<number[]>([])
  const [pluginState, setPluginState] =
    useState<PluginState>('idle')

  const toggleSelect = (id: number) => {
    setSelected((prev) =>
      prev.includes(id)
        ? prev.filter((i) => i !== id)
        : [...prev, id]
    )
  }

  const handleAdd = () => {
    if (selected.length === 0) return
    setPluginState('confirmAdd')
  }

  const confirmAdd = () => {
    setPluginState('adding')

    // abang - swap this for the real install call
    // POST /api/plugins/install { ids: selected }
    // keep the modal open until the response comes back, don't just trust the timeout
    setTimeout(() => {
      setSelected([])
      setPluginState('idle')
    }, 2500)
  }

  const handleDelete = () => {
    if (selected.length === 0) return
    setPluginState('confirmDelete')
  }

  const confirmDelete = () => {
    setPluginState('deleting')

    // abang - same deal, wire this to DELETE /api/plugins { ids: selected }
    // also need to handle partial failures if some plugins fail to delete
    setTimeout(() => {
      setSelected([])
      setPluginState('deleteSuccess')
    }, 2000)
  }

  const closeModal = () => setPluginState('idle')

  return (
    <main className="ml-[220px] flex-1 space-y-6">

      <PageHeader
        title="Monitoring Configuration"
        description="Manage all available plugins. View active monitoring checks"
      />

      <div className="grid md:grid-cols-4 gap-5">
        {/* these are hardcoded for now, hook up to /api/plugins/stats later */}
        <SummaryStatCard
          title="Available Plugins"
          value="50"
          subtitle="Nagios plugins"
          icon={Activity}
          gradient="linear-gradient(135deg,#FF8A00,#FF5C00)"
        />

        <SummaryStatCard
          title="Installed Plugins"
          value="15"
          subtitle="running plugins"
          icon={Activity}
          gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
        />

        <SummaryStatCard
          title="Active Monitoring Checks"
          value="6"
          subtitle="enabled"
          icon={Activity}
          gradient="linear-gradient(135deg,#FF4D4D,#DC2626)"
        />

        <SummaryStatCard
          title="Plugin Engine Status"
          value="running"
          subtitle=""
          icon={Activity}
          gradient="linear-gradient(135deg,#FFB100,#F59E0B)"
        />
      </div>

      <div className="flex gap-6 border-b border-white/10">
        <button
          type="button"
          onClick={() => setView('available')}
          className={`pb-3 text-sm transition ${
            view === 'available'
              ? 'border-b-2 border-white font-medium text-white'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Available Plugins
        </button>

        <button
          type="button"
          onClick={() => setView('installed')}
          className={`pb-3 text-sm transition ${
            view === 'installed'
              ? 'border-b-2 border-white font-medium text-white'
              : 'text-gray-500 hover:text-gray-300'
          }`}
        >
          Installed Plugins
        </button>
      </div>

      {view === 'available' ? (
        <div className="mt-4">
          <AvailablePluginsTable
            data={availablePlugins}
            selected={selected}
            onSelect={toggleSelect}
          />
        </div>
      ) : (
        <div className="mt-4">
          <InstalledPluginsTable
            data={installedPlugins}
            selected={selected}
            onSelect={toggleSelect}
          />
        </div>
      )}

      {view === 'available' && (
        <div className="flex gap-3">
          <button
            onClick={handleAdd}
            className="bg-[#ffb100] px-5 py-2 rounded-lg text-black font-medium"
          >
            Add Selected Plugins
          </button>

          <button
            onClick={handleDelete}
            className="bg-red-500 px-5 py-2 rounded-lg text-white"
          >
            Delete Plugins
          </button>
        </div>
      )}

      {pluginState !== 'idle' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">

          <div className="relative w-full max-w-sm rounded-3xl bg-white p-8 text-center shadow-xl">

            {pluginState !== 'adding' &&
              pluginState !== 'deleting' && (
                <button
                  onClick={closeModal}
                  className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
                >
                  <X className="h-5 w-5" />
                </button>
            )}

            {pluginState === 'confirmAdd' && (
              <>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-[#F4A90B]">
                  <HelpCircle className="h-7 w-7 text-white" />
                </div>

                <h2 className="text-lg font-semibold text-gray-900">
                  This action requires system reboot.
                </h2>

                <p className="mt-2 text-sm text-gray-500">
                  Are you sure you want to add the selected plugins? This action
                  will re-analyze all connected devices and update the current
                  network health status.
                </p>

                <div className="mt-6 flex justify-center gap-3">
                  <button
                    onClick={closeModal}
                    className="rounded-2xl border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>

                  <button
                    onClick={confirmAdd}
                    className="rounded-2xl bg-emerald-500 px-5 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                  >
                    Confirm
                  </button>
                </div>
              </>
            )}

            {pluginState === 'confirmDelete' && (
              <>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-red-500">
                  <HelpCircle className="h-7 w-7 text-white" />
                </div>

                <h2 className="text-lg font-semibold text-gray-900">
                  Confirm Plugin Deletion
                </h2>

                <p className="mt-2 text-sm text-gray-500">
                  Deleting this plugin will remove it from your available plugins
                  list. Do you want to continue?
                </p>

                <div className="mt-6 flex justify-center gap-3">
                  <button
                    onClick={closeModal}
                    className="rounded-2xl border border-gray-300 px-5 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>

                  <button
                    onClick={confirmDelete}
                    className="rounded-2xl bg-red-500 px-5 py-2 text-sm font-medium text-white hover:bg-red-600"
                  >
                    Confirm
                  </button>
                </div>
              </>
            )}

            {(pluginState === 'adding' ||
              pluginState === 'deleting') && (
              <>
                <div className="mx-auto mb-4 h-14 w-14 animate-spin rounded-full border-4 border-blue-200 border-t-blue-500" />

                <h2 className="text-lg font-semibold text-gray-900">
                  System rebooting
                </h2>

                <p className="mt-2 text-sm text-gray-500">
                  Please wait. Do not close the system.
                </p>
              </>
            )}

            {pluginState === 'deleteSuccess' && (
              <>
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-blue-500">
                  <CheckCircle2 className="h-8 w-8 text-white" />
                </div>

                <h2 className="text-lg font-semibold text-gray-900">
                  Deletion completed.
                </h2>

                <div className="mt-6 flex justify-center">
                  <button
                    onClick={closeModal}
                    className="rounded-2xl bg-emerald-500 px-8 py-2 text-sm font-medium text-white hover:bg-emerald-600"
                  >
                    OK
                  </button>
                </div>
              </>
            )}

          </div>
        </div>
      )}

    </main>
  )
}