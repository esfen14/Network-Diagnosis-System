import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import { DeviceInventoryPage } from '../pages/DeviceInventoryPage'

// devices.ts has 10 entries total, 8 belonging to R1 and 2 to R2, none to R3
// routers = ['R1', 'R2', 'R3']

function renderPage() {
  return render(
    <MemoryRouter>
      <DeviceInventoryPage />
    </MemoryRouter>,
  )
}

describe('DeviceInventoryPage', () => {
  it('renders without crashing', () => {
    renderPage()
  })

  it("shows 'Device Inventory' heading", () => {
    renderPage()
    expect(screen.getByText('Device Inventory')).toBeInTheDocument()
  })

  it("shows 'All Devices' tab button", () => {
    renderPage()
    expect(screen.getByRole('button', { name: 'All Devices' })).toBeInTheDocument()
  })

  it("shows 'Router' tab button", () => {
    renderPage()
    expect(screen.getByRole('button', { name: 'Router' })).toBeInTheDocument()
  })

  it("initially shows 'All Devices' table title", () => {
    renderPage()
    // DeviceTable renders an h2 with the title prop
    expect(screen.getByRole('heading', { name: 'All Devices' })).toBeInTheDocument()
  })

  it('clicking Router tab shows router filter buttons R1, R2, R3', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Router' }))
    expect(screen.getByRole('button', { name: 'R1' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'R2' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'R3' })).toBeInTheDocument()
  })

  it('clicking Router tab then R2 filters to R2 devices', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Router' }))
    fireEvent.click(screen.getByRole('button', { name: 'R2' }))
    // R2 devices are SRV-File1 and SRV-Mail1 (2 devices)
    expect(screen.getByText('Showing 2 devices')).toBeInTheDocument()
    expect(screen.getByText('SRV-File1')).toBeInTheDocument()
    expect(screen.getByText('SRV-Mail1')).toBeInTheDocument()
  })

  it('clicking All Devices tab after Router shows all devices again', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Router' }))
    fireEvent.click(screen.getByRole('button', { name: 'R2' }))
    fireEvent.click(screen.getByRole('button', { name: 'All Devices' }))
    // All 10 devices should show
    expect(screen.getByText('Showing 10 devices')).toBeInTheDocument()
  })

  it('DeviceTable shows device hostname data (R2)', () => {
    renderPage()
    // 'R2' appears multiple times: once as the hostName for device #D-002,
    // and also in the router column for several R1 devices. Use getAllByText.
    const r2Cells = screen.getAllByText('R2')
    expect(r2Cells.length).toBeGreaterThan(0)
  })

  it('shows correct device count in footer for all devices', () => {
    renderPage()
    expect(screen.getByText('Showing 10 devices')).toBeInTheDocument()
  })

  it('shows correct device count after switching to R1 router tab', () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Router' }))
    // R1 is the default activeRouter, and 8 devices belong to R1
    expect(screen.getByText('Showing 8 devices')).toBeInTheDocument()
  })
})
