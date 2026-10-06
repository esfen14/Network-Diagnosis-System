import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ apiGet: vi.fn(), apiPut: vi.fn() }))
vi.mock('../lib/api', () => http)

import { changePort, getDevicePorts } from '../lib/devicePortsApi'

describe('devicePortsApi', () => {
  beforeEach(() => {
    http.apiGet.mockReset().mockResolvedValue({})
    http.apiPut.mockReset().mockResolvedValue({})
  })

  it('reads a device\'s ports', async () => {
    await getDevicePorts(4)
    expect(http.apiGet).toHaveBeenCalledWith('/api/system/hosts/4/ports')
  })

  it('changes one port with the body of the action', async () => {
    await changePort(4, 'tcp', 22, { state: 'IGNORED' })
    await changePort(4, 'udp', 161, { service_name: 'snmp' })
    await changePort(7, 'tcp', 8080, { unpin: true })

    expect(http.apiPut).toHaveBeenNthCalledWith(1, '/api/system/hosts/4/ports/tcp/22', { state: 'IGNORED' })
    expect(http.apiPut).toHaveBeenNthCalledWith(2, '/api/system/hosts/4/ports/udp/161', { service_name: 'snmp' })
    expect(http.apiPut).toHaveBeenNthCalledWith(3, '/api/system/hosts/7/ports/tcp/8080', { unpin: true })
  })
})
