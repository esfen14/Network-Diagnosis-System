import type { ReactNode } from 'react'

export function LoginBackdrop({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden p-4">
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
      <div className="relative z-10 flex w-full justify-center">{children}</div>
    </div>
  )
}
