export default function PilotCTA({ compact = false }: { compact?: boolean }) {
  return <section aria-label="Request a shadow pilot" className={`rounded-xl border border-emerald-200 bg-emerald-50 ${compact ? "p-4" : "p-6"}`}>
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="max-w-2xl">
        <h2 className="font-semibold text-gray-900">Review a de-identified deviation with us</h2>
        <p className="mt-1 text-sm text-gray-600">Bring one investigation objective and a description of the records you can share. In a scoped shadow pilot, we aim to return a source-linked evidence inventory, competing hypotheses, unresolved questions and human-review tasks.</p>
        <p className="mt-2 text-xs text-gray-500">Start with a discussion; share records only after agreeing permissions and handling. Advisory review only; no autonomous manufacturing actions or guaranteed outcome.</p>
      </div>
      <a className="inline-flex rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800" href="https://calendar.app.google/EvGcEGs8SycQKR478" target="_blank" rel="noreferrer">Request a shadow pilot ↗</a>
    </div>
  </section>;
}
