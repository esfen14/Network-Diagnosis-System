import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import { useDevicePorts } from '../hooks/useDevicePorts'
import { port, ports } from './devicePortsFixtures'

const api = vi.hoisted(() => ({ getDevicePorts: vi.fn() }))
vi.mock('../lib/devicePortsApi', () => api)

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

beforeEach(() => {
  api.getDevicePorts.mockReset().mockResolvedValue(ports([port()]))
})

describe('useDevicePorts', () => {
  it('loads the device\'s ports', async () => {
    const { result } = renderHook(() => useDevicePorts(4))

    expect(result.current.isLoading).toBe(true)
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.data?.ports).toHaveLength(1)
    expect(result.current.error).toBeNull()
    expect(api.getDevicePorts).toHaveBeenCalledWith(4)
  })

  it('reports the server\'s message when loading fails', async () => {
    api.getDevicePorts.mockRejectedValue(new ApiError('Device not found.', 404))
    const { result } = renderHook(() => useDevicePorts(4))

    await waitFor(() => expect(result.current.error).toBe('Device not found.'))
    expect(result.current.data).toBeNull()
    expect(result.current.isLoading).toBe(false)
  })

  it('uses a plain message when the failure has none', async () => {
    api.getDevicePorts.mockRejectedValue('boom')
    const { result } = renderHook(() => useDevicePorts(4))

    await waitFor(() => expect(result.current.error).toBe('Unable to load the ports.'))
  })

  it('reloads on demand and keeps the old list while it does', async () => {
    const { result } = renderHook(() => useDevicePorts(4))
    await waitFor(() => expect(result.current.data).not.toBeNull())
    const second = deferred<ReturnType<typeof ports>>()
    api.getDevicePorts.mockReturnValueOnce(second.promise)

    act(() => result.current.reload())

    await waitFor(() => expect(result.current.isLoading).toBe(true))
    expect(result.current.data?.ports).toHaveLength(1)               // no flicker
    await act(async () => { second.resolve(ports([port(), port({ number: 80 })])) })
    await waitFor(() => expect(result.current.data?.ports).toHaveLength(2))
  })

  it('clears an earlier error when it loads again', async () => {
    api.getDevicePorts.mockRejectedValueOnce(new ApiError('Temporary failure', 500))
    const { result } = renderHook(() => useDevicePorts(4))
    await waitFor(() => expect(result.current.error).toBe('Temporary failure'))

    act(() => result.current.reload())

    await waitFor(() => expect(result.current.data).not.toBeNull())
    expect(result.current.error).toBeNull()
  })

  it('does not show one device\'s ports while another loads', async () => {
    const other = deferred<ReturnType<typeof ports>>()
    const { result, rerender } = renderHook(({ id }) => useDevicePorts(id), { initialProps: { id: 4 } })
    await waitFor(() => expect(result.current.data).not.toBeNull())
    api.getDevicePorts.mockReturnValueOnce(other.promise)

    rerender({ id: 9 })

    await waitFor(() => expect(result.current.data).toBeNull())
    await act(async () => { other.resolve(ports([port({ number: 3306 })], { id: 9 })) })
    await waitFor(() => expect(result.current.data?.device.id).toBe(9))
  })

  it('ignores an answer for a device that is no longer shown', async () => {
    const slow = deferred<ReturnType<typeof ports>>()
    api.getDevicePorts.mockReturnValueOnce(slow.promise)
    const { result, rerender } = renderHook(({ id }) => useDevicePorts(id), { initialProps: { id: 4 } })
    api.getDevicePorts.mockResolvedValueOnce(ports([port({ number: 3306 })], { id: 9 }))

    rerender({ id: 9 })
    await waitFor(() => expect(result.current.data?.device.id).toBe(9))
    await act(async () => { slow.resolve(ports([port({ number: 22 })], { id: 4 })) })

    expect(result.current.data?.device.id).toBe(9)
  })

  it('ignores a late answer after it is unmounted', async () => {
    const slow = deferred<ReturnType<typeof ports>>()
    api.getDevicePorts.mockReturnValueOnce(slow.promise)
    const { unmount } = renderHook(() => useDevicePorts(4))

    unmount()
    await act(async () => { slow.resolve(ports([port()])) })

    expect(api.getDevicePorts).toHaveBeenCalledTimes(1)
  })
})
