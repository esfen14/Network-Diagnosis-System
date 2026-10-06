import { useEffect, useState } from 'react'
import { getPluginInventory } from '../lib/pluginApi'

export type NcpaPluginState = 'unknown' | 'enabled' | 'not-enabled'

// Whether check_ncpa is on in Plugin Manager. NCPA checks are only monitored while it is
// enabled, so the deployment page warns when it is not. Any failure (including a user
// without plugin.view) leaves the state "unknown", which shows no warning.
export function useNcpaPluginState(): NcpaPluginState {
  const [state, setState] = useState<NcpaPluginState>('unknown')

  useEffect(() => {
    let cancelled = false
    getPluginInventory({ search: 'check_ncpa', per_page: 10, sort_by: 'name', order: 'asc' })
      .then((data) => {
        if (cancelled) return
        const plugin = data.items.find((item) => item.name === 'check_ncpa')
        if (!plugin) {
          setState('not-enabled')
          return
        }
        setState(plugin.status === 'Enabled' || plugin.status === 'Active' ? 'enabled' : 'not-enabled')
      })
      .catch(() => {
        if (!cancelled) setState('unknown')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return state
}
