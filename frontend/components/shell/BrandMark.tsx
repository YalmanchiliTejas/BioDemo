import Link from 'next/link';
import { cn } from '@/lib/cn';

/** Display the supplied brand artwork without modifying the original asset. */
export function BrandMark({ href = '/cmo', className, label = true }: { href?: string; className?: string; label?: boolean }) {
  return <Link href={href} aria-label="Sievance" className={cn('sievance-brand', !label && 'sievance-brand-symbol', className)}>
    <svg viewBox="145 300 280 440" role="img" aria-label="Sievance" className="sievance-artwork"><image href="/brand/sievance.png" width="1448" height="1086" /></svg>
    {label && <span className="sievance-wordmark">SIEVANCE</span>}
  </Link>;
}
