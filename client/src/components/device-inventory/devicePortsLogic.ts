// The rules of the Ports section that do not depend on React: how ports are grouped, which
// actions each port offers, what each action sends, and the wording of confirmations. They
// follow spec files/Device_Inventory_Requirements.md (§3 grouping, §5 actions, §6 pin).
import type { DevicePort, PortChange, PortProtocol, ServiceOption } from '../../types/devicePorts'

export type PortGroupId = 'attention' | 'monitored' | 'suggested' | 'stopped' | 'archived'

export const GROUP_TITLES: Record<PortGroupId, string> = {
  attention: 'Needs attention',
  monitored: 'Monitored',
  suggested: 'Suggested',
  stopped: 'Stopped',
  archived: 'Archived',
}

export type PortGroup = { id: PortGroupId; title: string; ports: DevicePort[] }

function groupOf(port: DevicePort): PortGroupId {
  switch (port.state) {
    case 'MONITORED':
    case 'MISSING':
      return 'monitored'
    case 'IGNORED':
      return 'stopped'
    case 'ARCHIVED':
      return 'archived'
    default:
      return port.reason?.code === 'not_used_as_intended' || port.reason?.code === 'held' ? 'attention' : 'suggested'
  }
}

const STATE_RANK: Record<string, number> = { MONITORED: 0, MISSING: 1 }

// Groups in the order of requirement §3; an empty group is left out. Inside a group ports are
// ordered Monitored before Missing, then TCP before UDP, then by port number.
export function groupPorts(ports: DevicePort[]): PortGroup[] {
  const order: PortGroupId[] = ['attention', 'monitored', 'suggested', 'stopped', 'archived']
  const buckets = new Map<PortGroupId, DevicePort[]>(order.map((id) => [id, []]))
  for (const port of ports) buckets.get(groupOf(port))!.push(port)

  return order
    .map((id) => ({
      id,
      title: GROUP_TITLES[id],
      ports: [...buckets.get(id)!].sort(
        (a, b) =>
          (STATE_RANK[a.state] ?? 2) - (STATE_RANK[b.state] ?? 2) ||
          Number(a.protocol !== 'tcp') - Number(b.protocol !== 'tcp') ||
          a.number - b.number,
      ),
    }))
    .filter((group) => group.ports.length > 0)
}

export type PortActionId =
  | 'acknowledge'
  | 'monitor'
  | 'ignore'
  | 'stop'
  | 'leave_suggested'
  | 'resume'
  | 'set_service'
  | 'remove_pin'

// The actions a port offers, in display order (requirement §5). For a flagged port "Acknowledge and
// monitor" replaces "Monitor", since both would do the same thing. Nothing is offered on an Archived
// port or on the NCPA port of a deployed agent. Callers hide all of these without system.hosts.edit.
export function actionsFor(port: DevicePort): PortActionId[] {
  if (port.state === 'ARCHIVED' || port.managed_by_ncpa) return []

  const actions: PortActionId[] = []
  if (port.state === 'SUGGESTED') {
    actions.push(port.reason?.code === 'not_used_as_intended' ? 'acknowledge' : 'monitor', 'ignore')
  } else if (port.state === 'MONITORED' || port.state === 'MISSING') {
    actions.push('stop', 'leave_suggested')
  } else if (port.state === 'IGNORED') {
    actions.push('resume')
  }
  actions.push('set_service')
  if (port.pinned) actions.push('remove_pin')
  return actions
}

export const ACTION_LABELS: Record<PortActionId, string> = {
  acknowledge: 'Acknowledge and monitor',
  monitor: 'Monitor',
  ignore: 'Ignore',
  stop: 'Stop monitoring',
  leave_suggested: 'Leave suggested',
  resume: 'Resume',
  set_service: 'Set service…',
  remove_pin: 'Remove pin',
}

// What each action sends to the port-edit route. Set service needs the chosen name.
export function requestFor(action: PortActionId, serviceName?: string): PortChange {
  switch (action) {
    case 'acknowledge':
      return { acknowledge_mismatch: true }
    case 'monitor':
    case 'resume':
      return { state: 'MONITORED' }
    case 'ignore':
    case 'stop':
      return { state: 'IGNORED' }
    case 'leave_suggested':
      return { state: 'SUGGESTED' }
    case 'remove_pin':
      return { unpin: true }
    case 'set_service':
      return { service_name: serviceName }
  }
}

const NEEDS_CONFIRMATION: PortActionId[] = ['ignore', 'stop', 'leave_suggested', 'remove_pin']

export function needsConfirmation(action: PortActionId) {
  return NEEDS_CONFIRMATION.includes(action)
}

export function portLabel(port: Pick<DevicePort, 'protocol' | 'number'>) {
  return `${port.protocol}/${port.number}`
}

// The wording of each confirmation (requirement §5 and §6). Remove pin adds the sentence for the
// port's state: a monitored port keeps its Nagios service, any other follows the last scan.
export function confirmationText(action: PortActionId, port: DevicePort, host: string): string {
  const label = portLabel(port)
  switch (action) {
    case 'ignore':
      return `Ignore ${label} on ${host}? It will not be monitored.`
    case 'stop':
      return `Stop monitoring ${port.service_name} on ${host}? Its Nagios service is removed; history is kept.`
    case 'leave_suggested':
      return `Leave ${label} suggested? Its Nagios service is removed and no plugin will monitor it again until you do.`
    case 'remove_pin': {
      const monitored = port.state === 'MONITORED' || port.state === 'MISSING'
      const effect = monitored
        ? 'Its Nagios service is not changed. If a later scan sees a different service, the current one is kept and a review item is recorded.'
        : 'The service goes back to what the last scan saw.'
      return `Let scans decide the service for ${label} on ${host} again? ${effect}`
    }
    default:
      return ''
  }
}

export const SERVICE_NAME_RULE = /^[a-z0-9][a-z0-9_-]{0,31}$/

export const SERVICE_NAME_HELP = "Use letters, digits, '-' or '_' (shown in lowercase; up to 32 characters, starting with a letter or digit)."

// The "Checked by" line of the Set service dialog (requirement §6): a known service leads to its check
// plugin; any other name is checked by the generic TCP plugin on TCP and skipped on UDP.
export function checkedBy(name: string, protocol: PortProtocol, options: ServiceOption[]): string {
  const known = options.find((option) => option.name === name && option.protocols.includes(protocol))
  if (known) return known.plugin
  return protocol === 'tcp'
    ? 'check_tcp (generic TCP check)'
    : 'Skipped: no check exists for this UDP service'
}

const IDENTIFIED_LABELS: Record<string, string> = {
  FINGERPRINT: 'Fingerprint',
  PORT_RULE: 'Port rule',
  USER: 'Pinned',
  PORT_HINT: 'Guess',
}

export function identifiedLabel(port: DevicePort) {
  return IDENTIFIED_LABELS[port.identified_by ?? 'PORT_HINT'] ?? 'Guess'
}

// "just now", "5 min ago", "3 h ago", "2 d ago"; the exact time is shown on hover.
export function relativeTime(iso: string | null, now: Date = new Date()): string {
  if (!iso) return '—'
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return iso
  const seconds = Math.max(0, Math.round((now.getTime() - then.getTime()) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.floor(hours / 24)} d ago`
}
