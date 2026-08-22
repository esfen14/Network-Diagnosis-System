import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import { ManageAccountsPage } from '../pages/ManageAccountsPage'

// users.ts breakdown (11 total):
//   active:    Marie Santos, Chloe Baltazar, Ella Dela Cruz, Lucas Mitchell, Joshua Vilar  → 5
//   inactive:  John Cruz, Mia Nicdao                                                       → 2
//   locked:    Michael Gonzales, Mark Santos                                               → 2
//   suspended: Marco Gomez, Nicholas Aguirre                                               → 2

function renderPage() {
  return render(
    <MemoryRouter>
      <ManageAccountsPage />
    </MemoryRouter>,
  )
}

describe('ManageAccountsPage', () => {
  it('renders without crashing', () => {
    renderPage()
  })

  it("shows 'User Management' heading", () => {
    renderPage()
    expect(screen.getByText('User Management')).toBeInTheDocument()
  })

  it('shows all 5 filter buttons', () => {
    renderPage()
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Active' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Inactive' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Locked' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Suspended' })).toBeInTheDocument()
  })

  it("'All' filter is active by default (has bg-white text-black classes)", () => {
    renderPage()
    const allButton = screen.getByRole('button', { name: 'All' })
    expect(allButton.className).toMatch(/bg-white/)
    expect(allButton.className).toMatch(/text-black/)
  })

  it("shows '+ Add User' button", () => {
    renderPage()
    expect(screen.getByRole('button', { name: '+ Add User' })).toBeInTheDocument()
  })

  it("shows 'Export' button", () => {
    renderPage()
    expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument()
  })

  it('shows all 11 users by default', () => {
    renderPage()
    expect(screen.getByText('Showing 11 users')).toBeInTheDocument()
  })

  it('shows specific user data from users.ts (Marie Santos)', () => {
    renderPage()
    expect(screen.getByText('Marie Santos')).toBeInTheDocument()
  })

  it("clicking 'Active' filter shows only active users (5)", () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Active' }))
    expect(screen.getByText('Showing 5 users')).toBeInTheDocument()
    // Active users should be visible
    expect(screen.getByText('Marie Santos')).toBeInTheDocument()
    expect(screen.getByText('Chloe Baltazar')).toBeInTheDocument()
    // Inactive user should not be visible
    expect(screen.queryByText('John Cruz')).not.toBeInTheDocument()
  })

  it("clicking 'All' after filtering restores all 11 users", () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Active' }))
    fireEvent.click(screen.getByRole('button', { name: 'All' }))
    expect(screen.getByText('Showing 11 users')).toBeInTheDocument()
  })

  it("clicking 'Inactive' shows only inactive users (2)", () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Inactive' }))
    expect(screen.getByText('Showing 2 users')).toBeInTheDocument()
    expect(screen.getByText('John Cruz')).toBeInTheDocument()
    expect(screen.getByText('Mia Nicdao')).toBeInTheDocument()
    expect(screen.queryByText('Marie Santos')).not.toBeInTheDocument()
  })

  it("clicking 'Locked' shows only locked users (2)", () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Locked' }))
    expect(screen.getByText('Showing 2 users')).toBeInTheDocument()
    expect(screen.getByText('Michael Gonzales')).toBeInTheDocument()
    expect(screen.getByText('Mark Santos')).toBeInTheDocument()
  })

  it("clicking 'Suspended' shows only suspended users (2)", () => {
    renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'Suspended' }))
    expect(screen.getByText('Showing 2 users')).toBeInTheDocument()
    expect(screen.getByText('Marco Gomez')).toBeInTheDocument()
    expect(screen.getByText('Nicholas Aguirre')).toBeInTheDocument()
  })
})
