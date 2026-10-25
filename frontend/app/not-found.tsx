import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-canvas px-4">
      <div className="max-w-md text-center">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary">404</p>
        <h1 className="mt-2 text-lg font-semibold text-text-primary">This record isn’t in the demo dataset</h1>
        <p className="mt-2 text-[13px] text-text-secondary">
          The sandbox contains campaign CMP-26-10 (batches MES-26071 to MES-26073), pump PM-204 and related records. Press ⌘K inside the workspace to search.
        </p>
        <div className="mt-5 flex justify-center gap-2">
          <Link href="/home" className="inline-flex items-center h-8 px-3 rounded-control bg-brand-teal text-white text-[13px] font-medium hover:bg-brand-teal-dark">Go to briefing</Link>
          <Link href="/" className="inline-flex items-center h-8 px-3 rounded-control border border-border-strong text-[13px] font-medium text-text-primary hover:bg-surface-secondary">Product overview</Link>
        </div>
      </div>
    </div>
  );
}
