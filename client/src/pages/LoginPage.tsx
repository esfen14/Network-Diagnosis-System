import { Eye, EyeOff, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { PinPointLogo } from '../components/login/PinPointLogo'

// Placeholder copy for the login screen's slider — swap with real
// marketing content whenever it's ready.
const slides = [
  {
    title: ['Next Generation', 'Infrastructure', 'Security'],
    description:
      'PinPoint transforms complex network data into simple, actionable insights. Detect faster, respond smarter, and stay online longer.',
  },
  {
    title: ['Real-Time', 'Network', 'Visibility'],
    description:
      'Monitor every host and service across your network from a single dashboard, with live status updates as they happen.',
  },
  {
    title: ['Automated', 'Discovery &', 'Deployment'],
    description:
      'Discover new devices automatically and roll out monitoring agents in minutes, not hours.',
  },
]

const SLIDE_INTERVAL_MS = 6000

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const sessionExpired = Boolean(
    (location.state as { sessionExpired?: boolean } | null)?.sessionExpired
  )

  const [showPassword, setShowPassword] = useState(false)
  const [rememberMe, setRememberMe] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const [activeSlide, setActiveSlide] = useState(0)
  const [showForgot, setShowForgot] = useState(false)

  useEffect(() => {
    const id = window.setInterval(() => {
      setActiveSlide((current) => (current + 1) % slides.length)
    }, SLIDE_INTERVAL_MS)

    return () => window.clearInterval(id)
  }, [])

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()

    try {
      setLoading(true)

      const response = await fetch('/api/user/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({
          email,
          password,
        }),
      })

      const data = await response.json()

      if (response.ok) {
        navigate('/dashboard')
      } else {
        alert(data.message || 'Login failed')
      }
    } catch (error) {
      console.error('Login Error:', error)
      alert('Unable to connect to server')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-end overflow-hidden">
      <img
        src="/images/login-bg-3514dc.png"
        alt=""
        className="absolute inset-0 h-full w-full object-cover"
      />

      <div
        className="absolute inset-0"
        style={{
          background:
            'linear-gradient(46deg, rgba(33, 33, 33, 0.84) 0%, rgba(66, 66, 66, 0.24) 100%)',
        }}
      />

      <div className="absolute left-27.5 top-45 z-10 hidden lg:block">
        <PinPointLogo />

        <div className="mt-12 max-w-85">
          <h2 className="text-[42px] font-bold leading-[0.95] text-white">
            {slides[activeSlide].title.map((line) => (
              <span key={line} className="block">{line}</span>
            ))}
          </h2>

          <p className="mt-6 text-[18px] leading-[1.4] text-white/90">
            {slides[activeSlide].description}
          </p>

          <div className="mt-10 flex gap-3">
            {slides.map((slide, index) => (
              <button
                key={slide.title.join(' ')}
                type="button"
                onClick={() => setActiveSlide(index)}
                aria-label={`Go to slide ${index + 1}`}
                className={`h-0.75 rounded-full transition-all ${
                  index === activeSlide ? 'w-12 bg-white' : 'w-8 bg-white/40 hover:bg-white/60'
                }`}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-12 flex gap-2">
        {slides.map((slide, index) => (
          <button
            key={slide.title.join(' ')}
            type="button"
            onClick={() => setActiveSlide(index)}
            aria-label={`Go to slide ${index + 1}`}
            className={`h-0.5 rounded-full transition-all ${
              index === activeSlide ? 'w-12 bg-white' : 'w-8 bg-white/40 hover:bg-white/60'
            }`}
          />
        ))}
      </div>

      <div className="relative z-10 m-6 w-full max-w-115 rounded-3xl bg-white p-10 shadow-2xl lg:mr-51.25">
        <header className="mb-8">
          <p className="text-xs tracking-tight text-black">WELCOME BACK</p>
          <h2 className="mt-1 text-[25px] font-medium leading-tight tracking-tight text-black">
            Log In to your Account
          </h2>
          {sessionExpired && (
            <p
              role="status"
              className="mt-4 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-800"
            >
              Your session expired due to inactivity. Please log in again.
            </p>
          )}
        </header>

        <form onSubmit={handleSubmit} className="flex flex-col gap-6">
          <div className="flex flex-col gap-5">
            <div className="relative">
              <label className="absolute -top-2.5 left-4 z-10 bg-white px-1.5 text-xs text-[#100F0F]">
                Email
              </label>

              <input
                type="email"
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-[30px] border border-[#100F0F] px-4 py-4 text-base text-black placeholder:text-gray-500 outline-none focus:border-black"
                required
              />
            </div>

            <div className="relative">
              <label className="absolute -top-2.5 left-4 z-10 bg-white px-1.5 text-xs text-[#100F0F]">
                Password
              </label>

              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="•••••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-[30px] border border-[#100F0F] px-4 py-4 pr-12 text-base text-black placeholder:text-pinpoint-input-border/60 outline-none focus:border-black"
                required
              />

              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-[#100F0F]"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <EyeOff className="h-4 w-4" />
                ) : (
                  <Eye className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-black">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 accent-pinpoint-btn"
              />
              Remember me
            </label>

            <button
              type="button"
              onClick={() => setShowForgot(true)}
              className="text-sm text-gray-600 hover:underline"
            >
              Forgot Password?
            </button>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-[30px] bg-pinpoint-btn py-4 text-xs font-bold tracking-wide text-white transition hover:bg-black disabled:cursor-not-allowed disabled:opacity-70"
          >
            {loading ? 'LOGGING IN...' : 'LOG IN'}
          </button>
        </form>
      </div>
      {showForgot && (
        <ForgotPasswordModal initialEmail={email} onClose={() => setShowForgot(false)} />
      )}
    </div>
  )
}

function ForgotPasswordModal({
  initialEmail,
  onClose,
}: {
  initialEmail: string
  onClose: () => void
}) {
  const [email, setEmail] = useState(initialEmail)
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null)

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setSubmitting(true)
    try {
      const response = await fetch('/api/user/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      })
      const data = await response.json().catch(() => ({}))
      setResult({
        ok: response.ok,
        message:
          data.message ||
          (response.ok ? 'An administrator has been notified.' : 'Unable to send the request.'),
      })
    } catch {
      setResult({ ok: false, message: 'Unable to connect to server' })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Forgot password"
    >
      <div className="relative w-full max-w-md rounded-3xl bg-white p-8 shadow-2xl">
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute right-5 top-5 text-gray-500 hover:text-black"
        >
          <X className="h-5 w-5" />
        </button>

        <h2 className="text-xl font-medium text-black">Forgot your password?</h2>
        <p className="mt-2 text-sm text-gray-600">
          Enter your account email. An administrator will be notified and will set a new password
          for you.
        </p>

        {result?.ok ? (
          <>
            <p role="status" className="mt-5 rounded-2xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
              {result.message}
            </p>
            <button
              type="button"
              onClick={onClose}
              className="mt-5 w-full rounded-[30px] bg-pinpoint-btn py-3 text-xs font-bold tracking-wide text-white hover:bg-black"
            >
              BACK TO LOG IN
            </button>
          </>
        ) : (
          <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4">
            <input
              type="email"
              aria-label="Email"
              placeholder="Enter your email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-[30px] border border-[#100F0F] px-4 py-3 text-base text-black outline-none focus:border-black"
              required
            />
            {result && !result.ok && (
              <p role="alert" className="text-sm text-red-600">{result.message}</p>
            )}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-[30px] bg-pinpoint-btn py-3 text-xs font-bold tracking-wide text-white hover:bg-black disabled:cursor-not-allowed disabled:opacity-70"
            >
              {submitting ? 'SENDING...' : 'REQUEST PASSWORD RESET'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
