export function PinPointLogo({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-center gap-4 ${className}`}>
      <svg
        width="80"
        height="66"
        viewBox="0 0 268 220"
        fill="none"
        aria-hidden
      >
        <circle cx="134" cy="110" r="90" fill="url(#logoGrad)" opacity="0.9" />
        <circle cx="134" cy="110" r="60" fill="none" stroke="white" strokeWidth="3" opacity="0.6" />
        <circle cx="134" cy="110" r="8" fill="white" />
        <line x1="134" y1="20" x2="134" y2="50" stroke="white" strokeWidth="2" opacity="0.5" />
        <line x1="134" y1="170" x2="134" y2="200" stroke="white" strokeWidth="2" opacity="0.5" />
        <line x1="44" y1="110" x2="74" y2="110" stroke="white" strokeWidth="2" opacity="0.5" />
        <line x1="194" y1="110" x2="224" y2="110" stroke="white" strokeWidth="2" opacity="0.5" />
        <defs>
          <linearGradient id="logoGrad" x1="44" y1="20" x2="224" y2="200">
            <stop stopColor="#30D158" />
            <stop offset="1" stopColor="#00F546" />
          </linearGradient>
        </defs>
      </svg>
      <div>
        <h1 className="text-5xl font-normal tracking-tight text-white underline decoration-white/30 underline-offset-4">
          PinPoint
        </h1>
        <p className="mt-1 text-2xl font-medium tracking-tight text-white/70">
          Diagnostic System
        </p>
      </div>
    </div>
  )
}
