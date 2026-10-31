'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Building2, Database, UserRound } from 'lucide-react';

export function SettingsFrame({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  const path = usePathname().replace(/\/$/, '');
  return <div className="workspace-page"><header className="page-heading"><div><div className="page-kicker">Workspace / Settings</div><h1>{title}</h1><p>{description}</p></div></header><nav className="settings-nav" aria-label="Settings">{[{ href: '/settings/profile', label: 'My profile', icon: UserRound }, { href: '/settings/organization', label: 'Organization & team', icon: Building2 }, { href: '/sources', label: 'Connections', icon: Database }].map(({ href, label, icon: Icon }) => <Link key={href} href={`${href}/`} aria-current={path === href ? 'page' : undefined}><Icon size={14} />{label}</Link>)}</nav>{children}</div>;
}
