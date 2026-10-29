import type { Metadata } from 'next';
import './landing.css';

export const metadata: Metadata = {
  title: { absolute: 'Manufacturing OS · The AI operating system for pharmaceutical manufacturing' },
  description: 'Connect plant systems read-only, investigate deviations with the evidence in view, and forecast process outcomes with physics-based models. Every proposed change waits for a named person to sign.',
};

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-canvas text-ink">{children}</div>;
}
