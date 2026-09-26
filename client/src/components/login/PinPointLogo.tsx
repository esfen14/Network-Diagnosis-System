export function PinPointLogo({ className = '' }: { className?: string }) {
  return (
    <div className={`flex items-center gap-4 ${className}`}>
      <img
        src="/favicon.svg"
        alt=""
        aria-hidden
        className="h-20 w-20 shrink-0 object-contain"
      />
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
