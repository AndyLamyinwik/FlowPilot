import BackendStatus from '../components/BackendStatus'

function BrandMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 36 36" fill="none" className="size-10 shrink-0">
      <rect width="36" height="36" rx="11" fill="currentColor" />
      <path d="M11 25V11h14M11 18h10" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="25" cy="25" r="3" fill="#B4D9C8" />
    </svg>
  )
}

export default function HomePage() {
  return (
    <div className="min-h-screen bg-[#f6f7f2] text-stone-900">
      <header className="border-b border-stone-200/80 bg-white/70">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-6 py-5 sm:px-10">
          <div className="flex items-center gap-3 text-emerald-900">
            <BrandMark />
            <span className="text-xl font-bold tracking-tight text-stone-900">FlowPilot</span>
          </div>
          <span className="rounded-full border border-stone-200 px-3 py-1.5 text-xs font-medium tracking-wide text-stone-500">Phase 01 · Foundation</span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-12 sm:px-10 sm:py-16">
        <div className="mb-10 max-w-2xl">
          <p className="mb-4 text-xs font-semibold tracking-[0.18em] text-emerald-800 uppercase">Your automation workspace</p>
          <h1 className="text-4xl leading-tight font-semibold tracking-[-0.04em] sm:text-5xl">A clear place to start.</h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-stone-600 sm:text-lg">
            FlowPilot is a lightweight, visual, self-hosted workflow automation platform. Built to keep your work simple and your data yours.
          </p>
          <a href="/editor" className="mt-6 inline-block rounded-xl bg-emerald-900 px-5 py-3 text-sm font-medium text-white hover:bg-emerald-800 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-700">Open Workflow Editor</a>
        </div>

        <div className="space-y-6">
          <BackendStatus />

          <section aria-labelledby="dashboard-title" className="overflow-hidden rounded-2xl border border-stone-200 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-100 px-6 py-5 sm:px-8">
              <h2 id="dashboard-title" className="text-lg font-semibold tracking-tight">Placeholder Dashboard</h2>
              <span className="text-xs font-medium text-stone-500">A fresh workspace</span>
            </div>
            <div className="flex min-h-72 flex-col items-center justify-center px-6 py-14 text-center">
              <div aria-hidden="true" className="mb-6 flex size-16 items-center justify-center rounded-2xl border border-emerald-100 bg-emerald-50 text-emerald-800">
                <svg viewBox="0 0 32 32" fill="none" className="size-8">
                  <rect x="5" y="6" width="22" height="21" rx="4" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M5 12h22M11 6v6M11 18h10M11 22h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold tracking-tight">Room for what comes next.</h3>
              <p className="mt-3 max-w-md text-sm leading-6 text-stone-500">Your dashboard starts here. Workflow tools and activity will arrive in a future phase.</p>
            </div>
          </section>
        </div>

        <footer className="mt-9 flex flex-wrap justify-between gap-3 text-xs leading-5 text-stone-500">
          <p>FlowPilot · Open source. Self-hosted. Yours.</p>
          <p>Project initialization · v0.1.0</p>
        </footer>
      </main>
    </div>
  )
}
