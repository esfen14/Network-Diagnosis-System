import { describe, expect, it } from 'vitest'
import {
  SERVICE_NAME_RULE,
  actionsFor,
  checkedBy,
  confirmationText,
  groupPorts,
  identifiedLabel,
  needsConfirmation,
  relativeTime,
  requestFor,
  type PortActionId,
} from '../components/device-inventory/devicePortsLogic'
import type { DevicePort, PortReasonCode } from '../types/devicePorts'
import { OPTIONS, port } from './devicePortsFixtures'

const suggested = (code: PortReasonCode, overrides: Partial<DevicePort> = {}) =>
  port({ state: 'SUGGESTED', reason: { code, text: `reason ${code}` }, ...overrides })

describe('groupPorts', () => {
  it('orders the groups as the requirement does and leaves empty ones out', () => {
    const groups = groupPorts([
      port({ number: 443, state: 'ARCHIVED' }),
      port({ number: 8080, state: 'IGNORED' }),
      suggested('plugin_not_enabled', { number: 3306 }),
      suggested('held', { number: 9100 }),
      port({ number: 22 }),
    ])

    expect(groups.map((g) => g.id)).toEqual(['attention', 'monitored', 'suggested', 'stopped', 'archived'])
    expect(groups.map((g) => g.title)).toEqual(['Needs attention', 'Monitored', 'Suggested', 'Stopped', 'Archived'])
  })

  it('omits a group with no ports', () => {
    expect(groupPorts([port()]).map((g) => g.id)).toEqual(['monitored'])
    expect(groupPorts([])).toEqual([])
  })

  it('puts a flagged or held Suggested port under Needs attention and the rest under Suggested', () => {
    const groups = groupPorts([
      suggested('not_used_as_intended', { number: 1 }),
      suggested('held', { number: 2 }),
      suggested('guessed', { number: 3 }),
      suggested('plugin_not_enabled', { number: 4 }),
      suggested('no_udp_plugin', { number: 5 }),
      suggested('pending', { number: 6 }),
    ])

    expect(groups.find((g) => g.id === 'attention')!.ports.map((p) => p.number)).toEqual([1, 2])
    expect(groups.find((g) => g.id === 'suggested')!.ports.map((p) => p.number)).toEqual([3, 4, 5, 6])
  })

  it('shows Monitored before Missing, then TCP before UDP, then by port number', () => {
    const [group] = groupPorts([
      port({ protocol: 'udp', number: 53 }),
      port({ number: 80, state: 'MISSING' }),
      port({ number: 443 }),
      port({ number: 22 }),
      port({ protocol: 'udp', number: 5, state: 'MISSING' }),
    ])

    expect(group.ports.map((p) => `${p.state}-${p.protocol}-${p.number}`)).toEqual([
      'MONITORED-tcp-22', 'MONITORED-tcp-443', 'MONITORED-udp-53', 'MISSING-tcp-80', 'MISSING-udp-5',
    ])
  })

  it('does not change the list it is given', () => {
    const input = [port({ number: 443 }), port({ number: 22 })]
    groupPorts(input)
    expect(input.map((p) => p.number)).toEqual([443, 22])
  })
})

describe('actionsFor', () => {
  const ids = (p: DevicePort) => actionsFor(p)

  it('offers Acknowledge and monitor instead of Monitor on a flagged port', () => {
    expect(ids(suggested('not_used_as_intended'))).toEqual(['acknowledge', 'ignore', 'set_service'])
  })

  it.each<PortReasonCode>(['held', 'guessed', 'plugin_not_enabled', 'no_udp_plugin', 'device_excluded', 'pending'])(
    'offers Monitor and Ignore on a Suggested port (%s)', (code) => {
      expect(ids(suggested(code))).toEqual(['monitor', 'ignore', 'set_service'])
    })

  it.each(['MONITORED', 'MISSING'] as const)('offers Stop and Leave suggested on a %s port', (state) => {
    expect(ids(port({ state }))).toEqual(['stop', 'leave_suggested', 'set_service'])
  })

  it('offers Resume on an Ignored port', () => {
    expect(ids(port({ state: 'IGNORED', reason: { code: 'stopped', text: 'x' } }))).toEqual(['resume', 'set_service'])
  })

  it('adds Remove pin only to a pinned port', () => {
    expect(ids(port({ pinned: true }))).toEqual(['stop', 'leave_suggested', 'set_service', 'remove_pin'])
    expect(ids(port({ pinned: false }))).not.toContain('remove_pin')
    expect(ids(suggested('held', { pinned: true }))).toEqual(['monitor', 'ignore', 'set_service', 'remove_pin'])
  })

  it('offers nothing on an Archived port', () => {
    expect(ids(port({ state: 'ARCHIVED', pinned: true }))).toEqual([])
  })

  it('offers nothing on the NCPA port of a deployed agent', () => {
    expect(ids(port({ managed_by_ncpa: true, pinned: true }))).toEqual([])
  })
})

describe('requestFor', () => {
  it.each<[PortActionId, object]>([
    ['acknowledge', { acknowledge_mismatch: true }],
    ['monitor', { state: 'MONITORED' }],
    ['resume', { state: 'MONITORED' }],
    ['ignore', { state: 'IGNORED' }],
    ['stop', { state: 'IGNORED' }],
    ['leave_suggested', { state: 'SUGGESTED' }],
    ['remove_pin', { unpin: true }],
  ])('%s sends %j', (action, body) => {
    expect(requestFor(action)).toEqual(body)
  })

  it('Set service sends the chosen name', () => {
    expect(requestFor('set_service', 'http')).toEqual({ service_name: 'http' })
  })
})

describe('confirmations', () => {
  it('asks only for Ignore, Stop, Leave suggested and Remove pin', () => {
    const asked = (['acknowledge', 'monitor', 'ignore', 'stop', 'leave_suggested', 'resume', 'set_service', 'remove_pin'] as PortActionId[])
      .filter(needsConfirmation)
    expect(asked).toEqual(['ignore', 'stop', 'leave_suggested', 'remove_pin'])
  })

  it('uses the wording of the requirement', () => {
    const p = port({ number: 8080, service_name: 'http-proxy' })

    expect(confirmationText('ignore', p, 'web-01')).toBe('Ignore tcp/8080 on web-01? It will not be monitored.')
    expect(confirmationText('stop', p, 'web-01')).toBe(
      'Stop monitoring http-proxy on web-01? Its Nagios service is removed; history is kept.')
    expect(confirmationText('leave_suggested', p, 'web-01')).toBe(
      'Leave tcp/8080 suggested? Its Nagios service is removed and no plugin will monitor it again until you do.')
  })

  it('tells a monitored port its Nagios service is not changed when the pin is removed', () => {
    const text = confirmationText('remove_pin', port({ state: 'MONITORED', pinned: true }), 'web-01')

    expect(text).toContain('Let scans decide the service for tcp/22 on web-01 again?')
    expect(text).toContain('Its Nagios service is not changed.')
    expect(text).toContain('a review item is recorded')
  })

  it.each(['SUGGESTED', 'IGNORED', 'ARCHIVED'] as const)('tells a %s port it goes back to the last scan', (state) => {
    expect(confirmationText('remove_pin', port({ state, pinned: true }), 'web-01')).toContain(
      'The service goes back to what the last scan saw.')
  })

  it('has no confirmation text for actions that do not ask', () => {
    expect(confirmationText('monitor', port(), 'web-01')).toBe('')
  })
})

describe('Set service helpers', () => {
  it.each(['ssh', 'http-alt', 'my_service', 'a', '9p', 'a'.repeat(32)])('accepts %s', (name) => {
    expect(SERVICE_NAME_RULE.test(name)).toBe(true)
  })

  it.each(['', 'SSH', '-ssh', '_x', 'has space', 'a'.repeat(33), 'ssh;rm', 'é'])('rejects %j', (name) => {
    expect(SERVICE_NAME_RULE.test(name)).toBe(false)
  })

  it('names the check plugin for a known service on its protocol', () => {
    expect(checkedBy('http', 'tcp', OPTIONS)).toBe('check_http')
    expect(checkedBy('snmp', 'udp', OPTIONS)).toBe('check_snmp')
  })

  it('uses the generic TCP check for any other TCP name', () => {
    expect(checkedBy('printer', 'tcp', OPTIONS)).toBe('check_tcp (generic TCP check)')
  })

  it('skips an unknown UDP name, and a known name used on the wrong protocol', () => {
    expect(checkedBy('printer', 'udp', OPTIONS)).toBe('Skipped: no check exists for this UDP service')
    expect(checkedBy('http', 'udp', OPTIONS)).toBe('Skipped: no check exists for this UDP service')
    expect(checkedBy('snmp', 'tcp', OPTIONS)).toBe('check_tcp (generic TCP check)')
  })
})

describe('labels and time', () => {
  it.each([
    ['FINGERPRINT', 'Fingerprint'], ['PORT_RULE', 'Port rule'], ['USER', 'Pinned'], ['PORT_HINT', 'Guess'], [null, 'Guess'],
  ] as const)('labels %s as %s', (identifiedBy, label) => {
    expect(identifiedLabel(port({ identified_by: identifiedBy }))).toBe(label)
  })

  const now = new Date('2026-10-05T12:00:00Z')
  it.each([
    ['2026-10-05T11:59:40Z', 'just now'],
    ['2026-10-05T11:55:00Z', '5 min ago'],
    ['2026-10-05T09:00:00Z', '3 h ago'],
    ['2026-10-03T12:00:00Z', '2 d ago'],
    ['2026-10-05T12:30:00Z', 'just now'],           // a clock slightly ahead is not "in the future"
  ])('shows %s as %s', (iso, text) => {
    expect(relativeTime(iso, now)).toBe(text)
  })

  it('shows a dash for a missing time and the raw text for an unreadable one', () => {
    expect(relativeTime(null)).toBe('—')
    expect(relativeTime('not a date')).toBe('not a date')
  })
})
