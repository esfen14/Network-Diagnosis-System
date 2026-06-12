import { Outlet } from 'react-router-dom'

import { Header } from './Header'

import { Sidebar } from './Sidebar'

export function AdminLayout() {

  return (

    <div className="flex min-h-screen bg-pinpoint-sidebar">
      <Sidebar />
      <main className="flex min-h-screen flex-1 flex-col bg-pinpoint-dark">
        <div className="ml-[215px]">
          <Header />
        </div>
        <div className="flex-1 overflow-y-auto px-4 pb-8">
          <Outlet />
        </div>
      </main>
    </div>
  )

}