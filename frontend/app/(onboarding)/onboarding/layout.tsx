import { BrandMark } from '@/components/shell/BrandMark';
import { SessionGate } from '@/components/shell/SessionGate';
import Link from 'next/link';
export default function OnboardingLayout({ children }: {
    children: React.ReactNode;
}) {
    return <SessionGate><div className="setup-shell onboarding-shell"><header className="setup-header"><BrandMark href="/"/><Link href="/dashboard/">Back to workspace →</Link></header>{children}</div></SessionGate>;
}
