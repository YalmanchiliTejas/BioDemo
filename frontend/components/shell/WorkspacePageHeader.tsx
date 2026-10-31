'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';
import { locate } from '@/lib/navigation';

/** Breadcrumb, title, description and page actions, derived from the navigation so every page reads the same way. */
export function WorkspacePageHeader({ title, description, actions, status, trail }: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  status?: ReactNode;
  /** Extra levels below the navigation destination, e.g. an open delivery. */
  trail?: string[];
}) {
  const place = locate(usePathname());
  const crumbs = place ? [place.group.label, place.item.label, ...(trail ?? [])] : trail ?? [];
  return <header className="page-heading">
    <div className="min-w-0">
      {crumbs.length > 1 && <nav aria-label="Breadcrumb" className="page-breadcrumb"><ol>{crumbs.map((crumb, i) => <li key={`${crumb}-${i}`}>
        {i === 1 && trail?.length && place ? <Link href={`${place.item.href}/`}>{crumb}</Link> : <span aria-current={i === crumbs.length - 1 ? 'page' : undefined}>{crumb}</span>}
        {i < crumbs.length - 1 && <ChevronRight size={12} aria-hidden />}
      </li>)}</ol></nav>}
      <div className="page-title"><h1>{title}</h1>{status}</div>
      {description && <p>{description}</p>}
    </div>
    {actions && <div className="page-heading-actions">{actions}</div>}
  </header>;
}
