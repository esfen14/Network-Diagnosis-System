import { beforeEach, describe, expect, it, vi } from 'vitest'

const http = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../lib/api', () => http)

import * as pluginApi from '../lib/pluginApi'

describe('pluginApi service-driven wrappers', () => {
  beforeEach(() => {
    http.apiGet.mockReset().mockResolvedValue({})
    http.apiPost.mockReset().mockResolvedValue({})
  })

  it('asks what enabling would monitor', async () => {
    await pluginApi.getEnablePreview(7)
    expect(http.apiGet).toHaveBeenCalledWith('/api/plugin/7/enable-preview')
  })

  it('lists a plugin\'s services with paging and search, leaving out empty values', async () => {
    await pluginApi.getPluginServices(7, { page: 2, per_page: 5, search: 'web' })
    expect(http.apiGet).toHaveBeenCalledWith('/api/plugin/7/services?page=2&per_page=5&search=web')

    await pluginApi.getPluginServices(7, { page: 1, per_page: 5, search: '' })
    expect(http.apiGet).toHaveBeenLastCalledWith('/api/plugin/7/services?page=1&per_page=5')
  })

  it('stops and resumes one port on one device', async () => {
    const ref = { device_id: 4, protocol: 'tcp' as const, port: 22 }
    await pluginApi.stopServiceMonitoring(7, ref)
    await pluginApi.resumeServiceMonitoring(7, ref)

    expect(http.apiPost).toHaveBeenNthCalledWith(1, '/api/plugin/7/services/stop', ref)
    expect(http.apiPost).toHaveBeenNthCalledWith(2, '/api/plugin/7/services/resume', ref)
  })

  it('no longer exposes the removed manual routes', () => {
    for (const name of ['getRunningChecks', 'getMonitoringTargets', 'getPluginConfigurations', 'applyPluginConfiguration']) {
      expect(name in pluginApi).toBe(false)
    }
  })
})
