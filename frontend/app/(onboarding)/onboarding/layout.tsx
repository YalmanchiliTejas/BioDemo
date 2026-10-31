import { BrandMark } from '@/components/shell/BrandMark';
import { SessionGate } from '@/components/shell/SessionGate';
import Link from 'next/link';
export default function OnboardingLayout({ children }: {
    children: React.ReactNode;
}) {
    return <SessionGate><div className="setup-shell"><header className="setup-header"><BrandMark href="/"/><Link href="/cmo">Go to workspace →</Link></header>{children}</div></SessionGate>;
}
