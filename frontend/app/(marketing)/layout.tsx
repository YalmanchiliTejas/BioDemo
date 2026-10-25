import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: { absolute: 'Manufacturing OS · Biomanufacturing intelligence with verifiable evidence' },
  description: 'Starts from your existing systems of record, shows the source behind every finding, and routes consequential actions to a named human reviewer.',
};

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-white text-slate-900">{children}</div>;
}
