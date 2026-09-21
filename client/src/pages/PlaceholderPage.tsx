type PlaceholderPageProps = {
  title: string
  description: string
}

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <main className="ml-55 flex-1">
    <div className="rounded-3xl bg-[#1a1f26] p-8 shadow-lg">
      <h1 className="text-2xl font-semibold text-white">{title}</h1>
      <p className="mt-2 text-gray-400">{description}</p>
      <div className="mt-8 flex h-48 items-center justify-center rounded-2xl border border-dashed border-white/20">
        <p className="text-sm text-white/40">
          PLACEHOLDER, DUPLICATE THIS PAGE FIRST BEFORE EDITING
          Edit App.tsx after
        </p>
      </div>
    </div>
    </main>
  )
}
