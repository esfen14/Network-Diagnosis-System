type PageHeaderProps = {
  title: string
  highlight?: string
  description: string
}

export function PageHeader({ title, highlight, description }: PageHeaderProps) {
  return (
    <header>
      <h1 className="text-[25px] font-bold leading-tight text-white">
        {title}
        {highlight && (
          <span className="ml-2 font-bold text-pinpoint-green">{highlight}</span>
        )}
      </h1>
      <p className="mt-1 text-base font-light text-white/55">{description}</p>
    </header>
  )
}
