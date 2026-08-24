import type { ReactNode } from 'react'

interface SettingsCardProps {
  title: string
  description?: string
  children: ReactNode
}

export function SettingsCard({ title, description, children }: SettingsCardProps) {
  return (
    <section className="rounded-3xl bg-[var(--card)] border border-[var(--border)] p-6 shadow-sm transition-colors duration-200">
      <div className="mb-7">
        <h2 className="text-base font-semibold text-[var(--text)]">{title}</h2>
        {description && <p className="mt-1 text-sm text-[var(--text-muted)]">{description}</p>}
      </div>
      {children}
    </section>
  )
}
