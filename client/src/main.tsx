// PLEASE WALANG GAGALAW NG KAHIT ANO DITO

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App'

import {
  SystemSettingsProvider,
} from './contexts/SystemSettingsContext'

createRoot(
  document.getElementById('root')!
).render(
  <StrictMode>
    <BrowserRouter>
      <SystemSettingsProvider>
        <App />
      </SystemSettingsProvider>
    </BrowserRouter>
  </StrictMode>,
)