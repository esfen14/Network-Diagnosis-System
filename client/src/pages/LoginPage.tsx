import { Eye, EyeOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
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

  const [showPassword, setShowPassword] = useState(false)
  const [rememberMe, setRememberMe] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const [activeSlide, setActiveSlide] = useState(0)

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
    </div>
  )
}