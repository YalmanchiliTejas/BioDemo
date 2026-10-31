import Link from 'next/link';
import { cn } from '@/lib/cn';

/** Display the supplied brand artwork without modifying the original asset. */
export function BrandMark({ href = '/cmo', className, label = true }: { href?: string; className?: string; label?: boolean }) {
  return <Link href={href} aria-label="Sievance" className={cn('sievance-brand', !label && 'sievance-brand-symbol', className)}>
    <img src="/brand/sievance.png" alt="Sievance" width="1448" height="1086" />
  </Link>;
}
