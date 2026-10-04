import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TimeRangeSelect } from '../components/network-health/TimeRangeSelect'
import { CpuLoadChart } from '../components/network-health/CpuLoadChart'

describe('TimeRangeSelect', () => {
  it('offers last 5 minutes, last hour, 6 hours, 24 hours and 7 days', () => {
    render(<TimeRangeSelect hours={24} onChange={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Time range' }))
    for (const label of ['Last 5 minutes', 'Last hour', 'Last 6 hours', 'Last 7 days']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })

  it('reports the chosen range', () => {
    const onChange = vi.fn()
    render(<TimeRangeSelect hours={24} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name: 'Time range' }))
    fireEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
    expect(onChange).toHaveBeenCalledWith(168)
  })

  it('is shown on the CPU load chart', () => {
    render(
      <CpuLoadChart
        load={{ configured: true, load1: [], load5: [], load15: [] }}
        hours={6}
        onHoursChange={() => {}}
        isLoading={false}
      />,
    )
    expect(screen.getByRole('button', { name: 'Time range' })).toHaveTextContent('Last 6 hours')
  })
})
