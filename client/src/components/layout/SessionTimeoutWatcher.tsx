import { useEffect, useRef } from 'react'
import { useNavigate, type NavigateFunction } from 'react-router-dom'
import { useSystemSettings } from '../../contexts/SystemSettingsContext'

// Logs the user out after `sessionTimeout` minutes (System Settings →
// Security) without keyboard, mouse, scroll or touch input. Background
// polling doesn't count as activity, so the back end can't detect idle
// time on its own while a page is open — it only enforces the timeout
// for tabs that stopped making requests (see enforce_session_timeout in
// server/app/api/user/login.py).
//
// The last-activity time is shared through localStorage so an active tab
// keeps other open tabs signed in too.

export const LAST_ACTIVITY_KEY = 'pinpoint-last-activity'

const ACTIVITY_EVENTS = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart', 'wheel'] as const
const ACTIVITY_WRITE_THROTTLE_MS = 5_000
const CHECK_INTERVAL_MS = 15_000

function readLastActivity(): number | null {
  try {
    const stored = localStorage.getItem(LAST_ACTIVITY_KEY)
    return stored ? Number(stored) : null
  } catch {
    return null
  }
}

function writeLastActivity(timestamp: number) {
  try {
    localStorage.setItem(LAST_ACTIVITY_KEY, String(timestamp))
  } catch {
    // Storage unavailable — this tab falls back to its in-memory value.
  }
}

// Mirrors the manual logout in Sidebar/Header: clear local state, then go
// to the login page, which shows a notice when `sessionExpired` is set.
function endSession(navigate: NavigateFunction, expired: boolean) {
  try {
    localStorage.clear()
    sessionStorage.clear()
  } catch {
    // Nothing to clear.
  }

  navigate('/login', { replace: true, state: { sessionExpired: expired } })
}

async function logoutAndEndSession(navigate: NavigateFunction) {
  try {
    await fetch('/api/user/logout', {
      method: 'POST',
      credentials: 'include',
    })
  } catch {
    // The back end expires the session on its own anyway.
  }

  endSession(navigate, true)
}

export function SessionTimeoutWatcher() {
  const navigate = useNavigate()
  const { savedSettings } = useSystemSettings()
  const timeoutMs = savedSettings.sessionTimeout * 60_000

  // navigate changes identity on every route change; keep the latest in a
  // ref so the effects below don't restart on each page navigation.
  const navigateRef = useRef(navigate)
  useEffect(() => {
    navigateRef.current = navigate
  }, [navigate])

  // Not signed in on page load: go to login without the "session expired"
  // notice. A leftover activity timestamp can't tell a timed-out session
  // from a browser that was simply closed, and showing the notice to
  // someone who never logged in is confusing. The notice is only shown
  // when the idle timer below ends a session this tab was using.
  useEffect(() => {
    writeLastActivity(Date.now())

    let cancelled = false

    fetch('/api/user/me', { credentials: 'include' })
      .then((res) => {
        if (!cancelled && res.status === 401) {
          endSession(navigateRef.current, false)
        }
      })
      .catch(() => {
        // Network failure isn't proof the session ended — leave it to the timer.
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let lastActivity = readLastActivity() ?? Date.now()
    let lastWrite = 0

    const recordActivity = () => {
      lastActivity = Date.now()
      if (lastActivity - lastWrite >= ACTIVITY_WRITE_THROTTLE_MS) {
        lastWrite = lastActivity
        writeLastActivity(lastActivity)
      }
    }

    const checkIdle = () => {
      const shared = readLastActivity()
      if (shared !== null) {
        lastActivity = Math.max(lastActivity, shared)
      }

      if (Date.now() - lastActivity >= timeoutMs) {
        void logoutAndEndSession(navigateRef.current)
      }
    }

    ACTIVITY_EVENTS.forEach((event) =>
      window.addEventListener(event, recordActivity, { passive: true })
    )
    const intervalId = window.setInterval(checkIdle, CHECK_INTERVAL_MS)

    return () => {
      ACTIVITY_EVENTS.forEach((event) =>
        window.removeEventListener(event, recordActivity)
      )
      window.clearInterval(intervalId)
    }
  }, [timeoutMs])

  return null
}
