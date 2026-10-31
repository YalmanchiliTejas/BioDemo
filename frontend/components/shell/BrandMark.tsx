import Link from 'next/link';
import { cn } from '@/lib/cn';

/** Transparent brand symbol shared with the favicon. */
export function BrandMark({ href = '/cmo', className, label = true }: { href?: string; className?: string; label?: boolean }) {
  return <Link href={href} aria-label="Sievance" className={cn('sievance-brand', !label && 'sievance-brand-symbol', className)}>
    <svg viewBox="365 124 675 1065" role="img" aria-label="Sievance" className="sievance-artwork"><image href="/brand/symbol-transparent.png" width="1278" height="1230" /></svg>
    {label && <span className="sievance-wordmark">SIEVANCE</span>}
  </Link>;
}
