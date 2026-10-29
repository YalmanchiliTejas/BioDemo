import Link from 'next/link';
import { cn } from '@/lib/cn';

export function BrandMark({ href = '/cmo', className, label = true }: { href?: string; className?: string; label?: boolean }) {
  return (
    <Link href={href} className={cn('flex items-center gap-2 min-w-0', className)} aria-label="Manufacturing OS">
      <svg viewBox="0 0 24 24" className="h-6 w-6 shrink-0" aria-hidden>
        <rect width="24" height="24" rx="6" fill="#0e7490" />
        <path d="M6 16.5V8l6 4 6-4v8.5" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="12" cy="12" r="1.4" fill="#a5f3fc" />
      </svg>
      {label && <span className="hidden truncate font-display text-[16px] font-semibold tracking-tight text-ink sm:inline">Manufacturing OS</span>}
    </Link>
  );
}
