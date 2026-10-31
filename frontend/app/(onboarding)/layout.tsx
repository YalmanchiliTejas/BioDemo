import { SessionGate } from '@/components/shell/SessionGate';
export default function OnboardingLayout({children}: {children: React.ReactNode}) { return <SessionGate>{children}</SessionGate>; }
